from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def ancestor_ids(self) -> list[int]:
        """Ids of the parents above this category (nearest first)."""
        ids = []
        node = self.parent
        while node is not None:
            ids.append(node.id)
            node = node.parent
        return ids

    def descendant_ids(self) -> list[int]:
        """This category's id plus every category below it."""
        ids = [self.id]
        frontier = [self.id]
        while frontier:
            frontier = list(Category.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
            ids.extend(frontier)
        return ids


class AttributeDefinition(models.Model):
    """A specification a category's products can have (e.g. Laptops: RAM, in GB).

    Definitions attached to a parent category apply to every category below it,
    so "warranty" can be defined once on Electronics. A laptop-only field such as
    processor is defined on Laptops and cannot be set on a phone.
    """

    class ValueType(models.TextChoices):
        TEXT = "TEXT", "Text"
        NUMBER = "NUMBER", "Number"

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="attribute_definitions")
    key = models.SlugField(max_length=50)
    label = models.CharField(max_length=100)
    value_type = models.CharField(max_length=10, choices=ValueType.choices, default=ValueType.TEXT)
    unit = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["category", "key"], name="unique_attribute_key_per_category")]
        ordering = ["category_id", "label"]

    def __str__(self):
        return f"{self.category.name}: {self.label}"


def definitions_for_category(category: Category):
    """Attribute definitions that apply to a category (its own and its ancestors')."""
    category_ids = [category.id, *category.ancestor_ids()]
    return AttributeDefinition.objects.filter(category_id__in=category_ids)
