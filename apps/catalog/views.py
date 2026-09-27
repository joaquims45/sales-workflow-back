from rest_framework import status, viewsets
from rest_framework.response import Response

from rag.indexer import build_index

from .models import Category, Product
from .serializers import (
    CategorySerializer,
    CategoryWriteSerializer,
    ProductSerializer,
    ProductWriteSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CategoryWriteSerializer
        return CategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category")  # for router name inference; get_queryset is authoritative

    def get_queryset(self):
        queryset = Product.objects.select_related("category")
        if self.action == "list":
            # The public storefront listing only ever shows active products;
            # admin actions (retrieve/update) can still reach inactive ones.
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductSerializer

    def perform_create(self, serializer):
        serializer.save()
        build_index()

    def perform_update(self, serializer):
        serializer.save()
        build_index()

    def create(self, request, *args, **kwargs):
        # ProductWriteSerializer takes `category` as a plain id; respond
        # with ProductSerializer's nested shape instead, so create/update
        # responses look like every other product the API returns.
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        self.perform_create(write_serializer)

        read_serializer = ProductSerializer(write_serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        self.perform_update(write_serializer)

        read_serializer = ProductSerializer(write_serializer.instance, context=self.get_serializer_context())
        return Response(read_serializer.data)
