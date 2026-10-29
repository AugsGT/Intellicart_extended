from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffRole
from apps.cart.services import get_active_cart
from apps.events.services import emit, session_key_from_request
from apps.products.models import Product
from apps.products.serializers import ProductSerializer
from apps.recommendations import services


def _user_and_session(request):
    user = request.user if request.user.is_authenticated else None
    return user, session_key_from_request(request)


def _respond(request, kind: str, recommended) -> Response:
    """Serialize recommended products (each with its reason) and record that a list was served."""
    user, session_key = _user_and_session(request)
    if recommended:
        emit(
            "RECOMMENDATION_GENERATED",
            user=user,
            session_key=session_key,
            payload={"kind": kind, "product_ids": [r.product.id for r in recommended]},
        )
    return Response([{**ProductSerializer(r.product).data, "reason": r.reason} for r in recommended])


class RecommendationView(APIView):
    """Recommendations are public: anonymous shoppers are identified by X-Session-Id."""

    permission_classes = [AllowAny]


def _active_product(pk) -> Product:
    return get_object_or_404(Product.objects.select_related("category"), pk=pk, status=Product.Status.ACTIVE)


class SimilarView(RecommendationView):
    def get(self, request, product_id):
        return _respond(request, "similar", services.similar_products(_active_product(product_id)))


class FrequentlyBoughtTogetherView(RecommendationView):
    def get(self, request, product_id):
        return _respond(request, "frequently_bought_together", services.frequently_bought_with(_active_product(product_id)))


class SubstitutesView(RecommendationView):
    """Empty unless the product is actually low or out of stock."""

    def get(self, request, product_id):
        return _respond(request, "substitutes", services.substitutes(_active_product(product_id)))


class RecentlyViewedView(RecommendationView):
    def get(self, request):
        user, session_key = _user_and_session(request)
        exclude = request.query_params.get("exclude")
        exclude_id = int(exclude) if exclude and exclude.isdigit() else None
        recommended = services.recently_viewed(user.id if user else None, session_key, exclude_id)
        return _respond(request, "recently_viewed", recommended)


class CartBasedView(RecommendationView):
    def get(self, request):
        user, session_key = _user_and_session(request)
        if user is None and not session_key:
            return Response([])
        cart = get_active_cart(user=user) if user else get_active_cart(session_key=session_key)
        return _respond(request, "cart_based", services.cart_based(cart))


class PersonalizedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _respond(request, "personalized", services.personalized(request.user))


class ClickSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=services.KINDS)
    product_id = serializers.IntegerField()


class ClickView(RecommendationView):
    """The storefront reports that a recommended product was clicked."""

    def post(self, request):
        serializer = ClickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, session_key = _user_and_session(request)
        product_id = serializer.validated_data["product_id"]
        get_object_or_404(Product, pk=product_id)
        emit(
            "RECOMMENDATION_CLICKED",
            user=user,
            session_key=session_key,
            entity_id=product_id,
            payload={"kind": serializer.validated_data["kind"], "product_id": product_id},
        )
        return Response({"detail": "tracked"}, status=202)


class StatsView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        return Response(services.stats())
