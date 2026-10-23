from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart import services


class AddItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1)


class UpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()


def current_cart(request):
    """The caller's cart: the logged-in user's, else the anonymous session's
    (X-Session-Id header). A user can never reach someone else's cart because the
    owner always comes from the token or from the caller's own session key."""
    if request.user.is_authenticated:
        return services.get_active_cart(user=request.user)
    session_key = request.headers.get("X-Session-Id", "").strip()
    if not session_key or len(session_key) > 64:
        raise services.CartError("X-Session-Id header is required")
    return services.get_active_cart(session_key=session_key)


class CartApiView(APIView):
    """Base class: public (anonymous carts allowed) and turns CartError into a JSON error."""

    permission_classes = [AllowAny]

    def handle_exception(self, exc):
        if isinstance(exc, services.CartError):
            return Response({"detail": exc.message}, status=exc.status_code)
        return super().handle_exception(exc)


class CartView(CartApiView):
    def get(self, request):
        return Response(services.cart_view(current_cart(request)))


class CartItemsView(CartApiView):
    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = current_cart(request)
        services.add_item(cart, serializer.validated_data["product_id"], serializer.validated_data["quantity"])
        return Response(services.cart_view(cart), status=status.HTTP_201_CREATED)


class CartItemDetailView(CartApiView):
    def patch(self, request, item_id):
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = current_cart(request)
        services.update_item(cart, item_id, serializer.validated_data["quantity"])
        return Response(services.cart_view(cart))

    def delete(self, request, item_id):
        cart = current_cart(request)
        services.remove_item(cart, item_id)
        return Response(services.cart_view(cart))


class CartMergeView(CartApiView):
    """Call right after login to bring the anonymous cart into the user's cart."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_key = request.headers.get("X-Session-Id", "").strip()
        if not session_key:
            raise services.CartError("X-Session-Id header is required")
        return Response(services.cart_view(services.merge_session_cart(request.user, session_key)))
