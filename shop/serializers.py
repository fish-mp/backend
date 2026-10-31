from rest_framework import serializers
from .models import (
    Brand, Category, Product, ProductImage, Collection, 
    Review, Favorite, Cart, CartItem, Order, OrderItem, Color
)

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
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
        images = list(obj.images.all())
        main = next((image for image in images if image.is_main), images[0] if images else None)
        return ProductImageSerializer(main, context=self.context).data if main else None

class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Полный сериалайзер для карточки товара
    """
    brand = BrandSerializer(read_only=True)
    color = ColorSerializer(read_only=True)
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
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return 'Покупатель'
    
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
    product_id = serializers.PrimaryKeyRelatedField(source='product', queryset=Product.objects.filter(is_available=True), write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        product = attrs.get('product')
        existing = Favorite.objects.filter(user=user, product=product)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError({'product_id': 'Товар уже в избранном.'})
        return attrs

    class Meta:
        model = Favorite
        fields = ['id', 'user', 'product', 'product_id', 'created_at']
        read_only_fields = ['user', 'created_at']

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(source='product', queryset=Product.objects.filter(is_available=True), write_only=True)
    quantity = serializers.IntegerField(min_value=1, max_value=10000, default=1)

    def validate(self, attrs):
        product = attrs.get('product') or (self.instance.product if self.instance else None)
        if self.instance and product.pk != self.instance.product_id:
            raise serializers.ValidationError({'product_id': 'Для другого товара создайте новую позицию корзины.'})
        quantity = attrs.get('quantity', self.instance.quantity if self.instance else 1)
        if not product or not product.is_available or not product.is_in_stock or quantity > product.stock_quantity:
            raise serializers.ValidationError({'quantity': 'Товар недоступен или запрошено больше, чем есть на складе.'})
        return attrs

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'total_price']

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
    product_name = serializers.SerializerMethodField()

    def get_product_name(self, obj):
        return obj.product_name or (obj.product.name if obj.product else 'Удалённый товар')
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'price', 'quantity']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'status', 'total_amount', 'created_at', 'items',
            'email', 'phone', 'city', 'street', 'house', 'apartment',
            'postal_code', 'offer_accepted', 'confirmation_url', 'delivery_method', 'delivery_cost', 'beyond_mkad',
        ]
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    privacy_consent = serializers.JSONField(required=False, write_only=True)
    email = serializers.EmailField(max_length=254)
    phone = serializers.RegexField(r'^\+?[\d\s()\-]{10,20}$', max_length=20)
    delivery_method = serializers.ChoiceField(choices=['pickup', 'delivery'], default='pickup')
    beyond_mkad = serializers.BooleanField(default=False)
    offer_accepted = serializers.BooleanField()
    city = serializers.CharField(max_length=100, allow_blank=True, default='')
    street = serializers.CharField(max_length=150, allow_blank=True, default='')
    house = serializers.CharField(max_length=30, allow_blank=True, default='')
    apartment = serializers.CharField(max_length=30, allow_blank=True, default='')
    postal_code = serializers.CharField(max_length=20, allow_blank=True, default='')

    def validate(self, attrs):
        from legal.catalog import validate_consent
        validate_consent(attrs.get('privacy_consent'), 'checkout')
        if not attrs['offer_accepted']:
            raise serializers.ValidationError({'offer_accepted': 'Необходимо согласие с публичной офертой.'})
        if attrs['delivery_method'] == 'delivery':
            missing = {field: 'Обязательное поле для доставки.' for field in ['city', 'street', 'house'] if not attrs[field]}
            if missing:
                raise serializers.ValidationError(missing)
        return attrs
