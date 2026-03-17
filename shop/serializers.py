from rest_framework import serializers
from .models import (
    Brand, Category, Product, ProductImage, Collection, 
    Review, Favorite, Cart, CartItem, Order, OrderItem
)

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'parent_name']

class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.ImageField(source='image', read_only=True) # Фронту часто нужен URL или поле напрямую

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'image_url', 'is_main']

class ProductListSerializer(serializers.ModelSerializer):
    """
    Упрощенный сериалайзер для списка товаров (чтобы не грузить базу лишними запросами)
    """
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    main_image = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'price', 'short_description', 
            'brand_name', 'main_image', 'average_rating', 'is_in_stock'
        ]

    def get_main_image(self, obj):
        # Берем первую картинку или помеченную как is_main
        main = obj.images.filter(is_main=True).first()
        if not main:
            main = obj.images.first()
        return ProductImageSerializer(main).data if main else None

class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Полный сериалайзер для карточки товара
    """
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    average_rating = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = '__all__'

class CollectionSerializer(serializers.ModelSerializer):
    products = ProductListSerializer(many=True, read_only=True)

    class Meta:
        model = Collection
        fields = '__all__'

class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True) 
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'product', 'product_name', 'user', 'score', 'text', 'created_at']
        read_only_fields = ['id', 'user', 'created_at', 'product_name']
        
    def validate_score(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Оценка должна быть от 1 до 5.")
        return value

class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True) 
    product_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'user', 'product', 'product_id', 'created_at']
        read_only_fields = ['user', 'created_at']

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'total_price']

    def get_total_price(self, obj):
        return obj.quantity * obj.product.price

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_cart_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total_cart_price', 'created_at']
        read_only_fields = ['user']

    def get_total_cart_price(self, obj):
        return sum(item.total_price for item in obj.items.all())

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'price', 'quantity']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'user', 'status', 'total_amount', 'created_at', 'items']
        read_only_fields = ['user', 'total_amount', 'created_at']
