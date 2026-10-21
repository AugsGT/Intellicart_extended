from rest_framework import serializers

from apps.categories.models import AttributeDefinition, Category


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeDefinition
        fields = ["id", "category", "key", "label", "value_type", "unit"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent"]

    def validate_parent(self, parent):
        if self.instance and parent and self.instance.id in [parent.id, *parent.ancestor_ids()]:
            raise serializers.ValidationError("A category cannot be placed under itself")
        return parent
