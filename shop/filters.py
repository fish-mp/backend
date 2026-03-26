import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    weight_min = django_filters.NumberFilter(field_name="weight", lookup_expr="gte")
    weight_max = django_filters.NumberFilter(field_name="weight", lookup_expr="lte")

    length_min = django_filters.NumberFilter(field_name="length", lookup_expr="gte")
    length_max = django_filters.NumberFilter(field_name="length", lookup_expr="lte")

    width_min = django_filters.NumberFilter(field_name="width", lookup_expr="gte")
    width_max = django_filters.NumberFilter(field_name="width", lookup_expr="lte")

    height_min = django_filters.NumberFilter(field_name="height", lookup_expr="gte")
    height_max = django_filters.NumberFilter(field_name="height", lookup_expr="lte")

    class Meta:
        model = Product
        fields = [
            'category',
            'brand',
            'color',
            'is_in_stock',
            'is_available',
            'collections',
        ]