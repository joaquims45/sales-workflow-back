from django.utils.text import slugify
from rest_framework import serializers

from .models import Category, Product


def _unique_slug(queryset, base_slug: str, exclude_pk=None) -> str:
    """Appends -2, -3, ... until the slug doesn't collide.

    Overriding `slug` on the write serializers (below) drops the
    UniqueValidator DRF would otherwise auto-generate from the model
    field's `unique=True` — this is what actually enforces uniqueness now.
    Auto-disambiguating instead of hard-failing is friendlier for an admin
    form that's just deriving the slug from the name behind the scenes.
    """

    slug = base_slug
    suffix = 2
    while queryset.filter(slug=slug).exclude(pk=exclude_pk).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class CategoryWriteSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False)

    class Meta:
        model = Category
        fields = ["id", "name", "slug"]

    def validate(self, attrs):
        name = attrs.get("name") or getattr(self.instance, "name", None)
        base_slug = attrs.get("slug") or (slugify(name) if name else None)
        if base_slug:
            exclude_pk = self.instance.pk if self.instance else None
            attrs["slug"] = _unique_slug(Category.objects.all(), base_slug, exclude_pk)
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "features",
            "use_cases",
            "semantic_tags",
            "price",
            "stock",
            "is_active",
        ]


class ProductWriteSerializer(serializers.ModelSerializer):
    """Accepts `category` as a plain id (unlike ProductSerializer's nested,
    read-only representation) and fills in `slug` from `name` when omitted,
    so the admin form doesn't need to ask for it.
    """

    slug = serializers.SlugField(required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "features",
            "use_cases",
            "semantic_tags",
            "price",
            "stock",
            "is_active",
        ]

    def validate(self, attrs):
        name = attrs.get("name") or getattr(self.instance, "name", None)
        base_slug = attrs.get("slug") or (slugify(name) if name else None)
        if base_slug:
            exclude_pk = self.instance.pk if self.instance else None
            attrs["slug"] = _unique_slug(Product.objects.all(), base_slug, exclude_pk)
        return attrs
