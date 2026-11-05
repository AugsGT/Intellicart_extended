import re

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import STAFF_ROLES, IsStaffRole
from apps.audit import services as audit
from apps.orders import services
from apps.orders.models import Order
from apps.orders.serializers import CheckoutSerializer, OrderSerializer, StatusUpdateSerializer


IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")


class OrderApiView(APIView):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, services.CheckoutError):
            return Response({"detail": exc.message}, status=exc.status_code)
        return super().handle_exception(exc)


class OrderListCreateView(generics.ListAPIView, OrderApiView):
    """GET: the logged-in customer's own orders. POST: checkout."""

    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        payment_method = data.pop("payment_method")
        card_number = data.pop("card_number")
        key = request.headers.get("Idempotency-Key", "").strip()
        if key and not IDEMPOTENCY_KEY.fullmatch(key):
            return Response({"detail": "Idempotency-Key must be 1-64 letters, digits, '-' or '_'"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = services.checkout(request.user, data, payment_method, card_number, idempotency_key=key)
        except services.PaymentDeclined as declined:
            body = {"detail": "Payment was declined", "order": OrderSerializer(declined.order).data}
            return Response(body, status=status.HTTP_402_PAYMENT_REQUIRED)
        replayed = getattr(order, "replayed", False)
        # A repeated request gets the original order back (200) instead of creating another (201).
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView, OrderApiView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        # Customers only ever see their own orders; anyone else's id is a 404.
        orders = Order.objects.prefetch_related("items")
        if self.request.user.role in STAFF_ROLES:
            return orders
        return orders.filter(user=self.request.user)


class OrderCancelView(OrderApiView):
    """A customer may cancel their own order while it is still CONFIRMED (not shipped)."""

    def post(self, request, pk):
        own = None if request.user.role in STAFF_ROLES else request.user
        if own is not None:
            order = Order.objects.filter(pk=pk, user=own).first()
            if order is not None and order.status != Order.Status.CONFIRMED:
                return Response({"detail": "Only confirmed orders can be cancelled"}, status=status.HTTP_400_BAD_REQUEST)
        order = services.change_status(pk, Order.Status.CANCELLED, user=own)
        audit.record(request, "ORDER_CANCELLED", f"Order #{order.id} cancelled by {'staff' if own is None else 'the customer'}",
                     entity_type="order", entity_id=order.id, details={"total": str(order.total), "customer_id": order.user_id})
        return Response(OrderSerializer(order).data)


class OrderStaffListView(generics.ListAPIView):
    """Operations console: every order (optionally ?status=)."""

    permission_classes = [IsStaffRole]
    serializer_class = OrderSerializer

    def get_queryset(self):
        orders = Order.objects.select_related("user").prefetch_related("items")
        wanted = self.request.query_params.get("status")
        return orders.filter(status=wanted) if wanted else orders


class OrderStatusView(OrderApiView):
    permission_classes = [IsStaffRole]

    def patch(self, request, pk):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous = Order.objects.filter(pk=pk).values_list("status", flat=True).first()
        order = services.change_status(pk, serializer.validated_data["status"])
        audit.record(request, "ORDER_CANCELLED" if order.status == Order.Status.CANCELLED else "ORDER_STATUS_CHANGED",
                     f"Order #{order.id}: {previous} -> {order.status}", entity_type="order", entity_id=order.id,
                     details={"from": previous, "to": order.status, "customer_id": order.user_id})
        return Response(OrderSerializer(order).data)
