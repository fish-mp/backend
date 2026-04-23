from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ProductFilter
from shop.models import (
    Brand, Category, Color, Product, Collection, 
    Review, Favorite, Cart, CartItem, Order, OrderItem
)
from shop.serializers import (
    BrandSerializer, CategorySerializer, ColorSerializer, ProductListSerializer, ProductDetailSerializer,
    CollectionSerializer, ReviewSerializer, FavoriteSerializer,
    CartSerializer, CartItemSerializer, OrderSerializer
)

class IsOwnerOrReadOnly(IsAuthenticatedOrReadOnly):
    """
    Разрешает редактирование только автору объекта.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        return obj.user == request.user


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

class ColorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Color.objects.all()
    serializer_class = ColorSerializer

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.select_related('brand', 'category', 'color').prefetch_related('images').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'name']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Collection.objects.prefetch_related('products').all()
    serializer_class = CollectionSerializer

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('user', 'product').all()
    serializer_class = ReviewSerializer
    permission_classes = [IsOwnerOrReadOnly]
    
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product'] 

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        cart = Cart.objects.get(user=self.request.user)
        return CartItem.objects.filter(cart=cart)

    def perform_create(self, serializer):
        cart = Cart.objects.get(user=self.request.user)
        product_id = self.request.data.get('product')
        existing_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
        
        if existing_item:
            existing_item.quantity += int(self.request.data.get('quantity', 1))
            existing_item.save()
            return Response(self.get_serializer(existing_item).data, status=status.HTTP_200_OK)
        else:
            serializer.save(cart=cart)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

class OrderViewSet(viewsets.ModelViewSet):
      serializer_class = OrderSerializer
      permission_classes = [IsAuthenticated]

      def get_queryset(self):
          return Order.objects.filter(user=self.request.user)

      def create(self, request, *args, **kwargs):
          # Логика оформления заказа:
          # 1. Берем корзину юзера
          # 2. Создаем заказ
          # 3. Переносим items из CartItem в OrderItem
          # 4. Очищаем корзину

          cart = Cart.objects.get(user=request.user)
          if not cart.items.exists():
              return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

          cart_items = list(cart.items.select_related('product').all())
          total_amount = sum(item.product.price * item.quantity for item in cart_items)

          order = Order.objects.create(user=request.user, status='new', total_amount=total_amount)

          for item in cart_items:
              OrderItem.objects.create(
                  order=order,
                  product=item.product,
                  price=item.product.price,
                  quantity=item.quantity
              )

          # Очищаем корзину
          cart.items.all().delete()

          serializer = self.get_serializer(order)
          return Response(serializer.data, status=status.HTTP_201_CREATED)
