from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrReadOnly
from apps.audit import services as audit
from apps.events.services import emit, session_key_from_request
from apps.products import services
from apps.products.models import Product
from apps.products.serializers import ProductSerializer


def _staff_can_see_archived(request) -> bool:
    user = request.user
    wants_all = request.query_params.get("status") == "all"
    return bool(wants_all and user.is_authenticated and user.role in (User.Role.ADMIN, User.Role.OPERATIONS))


def _emit_browsing_event(request, event_type: str, payload: dict, entity_id=None) -> None:
    """Record that someone viewed a product or searched. Anonymous shoppers are
    identified by their X-Session-Id. The outbox write is a small insert on a read path."""
    user = request.user if request.user.is_authenticated else None
    emit(event_type, user=user, session_key=session_key_from_request(request), entity_id=entity_id, payload=payload)


class ProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = ProductSerializer

    def get_queryset(self):
        return services.search_products(self.request.query_params, include_archived=_staff_can_see_archived(self.request))

    def perform_create(self, serializer):
        product = serializer.save()
        audit.record(self.request, "PRODUCT_CREATED", f"Created product {product.name}", entity_type="product", entity_id=product.id,
                     details={"name": product.name, "price": str(product.price), "category": product.category_id, "initial_stock": product.stock})

    def list(self, request, *args, **kwargs):
        query = (request.query_params.get("q") or "").strip()
        if query:
            _emit_browsing_event(request, "PRODUCT_SEARCHED", payload={"query": query[:200]})
        return super().list(request, *args, **kwargs)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = ProductSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # Archived products stay reachable by id for order history; the list hides them.
        return Product.objects.select_related("category").prefetch_related("attributes__definition")

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        _emit_browsing_event(request, "PRODUCT_VIEWED", entity_id=int(kwargs["pk"]), payload={"product_id": int(kwargs["pk"])})
        return response

    TRACKED_FIELDS = ("name", "description", "price", "category_id", "brand", "image", "low_stock_threshold")

    def perform_update(self, serializer):
        before = {f: getattr(serializer.instance, f) for f in self.TRACKED_FIELDS}
        product = serializer.save()
        changes = audit.changed_fields(before, {f: getattr(product, f) for f in self.TRACKED_FIELDS})
        if changes:
            audit.record(self.request, "PRODUCT_UPDATED", f"Edited product {product.name}: {', '.join(changes)}",
                         entity_type="product", entity_id=product.id, details={"changes": changes})

    def destroy(self, request, *args, **kwargs):
        # Products are archived, never deleted: orders and history point at them.
        product = self.get_object()
        product.status = Product.Status.ARCHIVED
        product.save(update_fields=["status", "updated_at"])
        audit.record(request, "PRODUCT_ARCHIVED", f"Archived product {product.name}", entity_type="product", entity_id=product.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
