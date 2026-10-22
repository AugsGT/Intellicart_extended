from django.db.models import ProtectedError
from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminOrReadOnly
from apps.audit import services as audit
from apps.categories.models import AttributeDefinition, Category
from apps.categories.serializers import AttributeDefinitionSerializer, CategorySerializer


class CategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    pagination_class = None  # the whole tree is small and the UI needs all of it

    def perform_create(self, serializer):
        category = serializer.save()
        audit.record(self.request, "CATEGORY_CREATED", f"Created category {category.name}", entity_type="category", entity_id=category.id)


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def perform_update(self, serializer):
        category = serializer.save()
        audit.record(self.request, "CATEGORY_UPDATED", f"Edited category {category.name}", entity_type="category", entity_id=category.id)

    def perform_destroy(self, instance):
        details = {"name": instance.name}
        pk = instance.pk
        instance.delete()
        audit.record(self.request, "CATEGORY_DELETED", f"Deleted category {details['name']}", entity_type="category", entity_id=pk)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "Category still has products or subcategories"}, status=status.HTTP_400_BAD_REQUEST
            )


class CategoryAttributesView(generics.ListAPIView):
    """Which specifications apply to a category (used by the admin form and the AI advisor)."""

    permission_classes = [IsAdminOrReadOnly]
    serializer_class = AttributeDefinitionSerializer
    pagination_class = None

    def get_queryset(self):
        from apps.categories.models import definitions_for_category

        category = generics.get_object_or_404(Category, pk=self.kwargs["pk"])
        return definitions_for_category(category)


class AttributeDefinitionCreateView(generics.CreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = AttributeDefinitionSerializer
    queryset = AttributeDefinition.objects.all()

    def perform_create(self, serializer):
        definition = serializer.save()
        audit.record(self.request, "ATTRIBUTE_CREATED", f"Created specification field {definition.label} for {definition.category.name}",
                     entity_type="attribute", entity_id=definition.id)
