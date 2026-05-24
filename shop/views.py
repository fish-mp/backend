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
from rest_framework.views import APIView
from yookassa import Configuration, Payment
from django.conf import settings
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse, JsonResponse
import json


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
    
@method_decorator(csrf_exempt, name='dispatch')
class YooKassaWebhookView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        try:
            event = json.loads(request.body)
            if event.get('event') == 'payment.succeeded':
                payment_id = event['object']['id']
                # Обновляем статус заказа
                Order.objects.filter(payment_id=payment_id, status='pending').update(status='paid')
            return HttpResponse(status=200)
        except Exception as e:
            # Логируем ошибку, но возвращаем 200, чтобы ЮKassa не повторяла
            return HttpResponse(status=200)
        
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
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return CartItem.objects.filter(cart=cart)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        cart, _ = Cart.objects.get_or_create(user=request.user)
        
        product_id = serializer.validated_data.get('product_id')
        quantity_to_add = serializer.validated_data.get('quantity', 1)
        
        existing_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
        
        if existing_item:
            existing_item.quantity += quantity_to_add
            existing_item.save()
            return Response(
                self.get_serializer(existing_item).data, 
                status=status.HTTP_200_OK
            )
        else:
            serializer.save(cart=cart)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, 
                status=status.HTTP_201_CREATED, 
                headers=headers
            )

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        cart = Cart.objects.get(user=request.user)
        if not cart.items.exists():
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = list(cart.items.select_related('product').all())
        total_amount = sum(item.product.price * item.quantity for item in cart_items)

        # 1. Создаём заказ со статусом "pending"
        order = Order.objects.create(
            user=request.user,
            status='pending',
            total_amount=total_amount
        )

        # 2. Переносим товары в OrderItem
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                price=item.product.price,
                quantity=item.quantity
            )

        
         Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

        # 3. Создаём платёж в ЮKassa (конфигурация уже выполнена глобально в начале файла)
        payment = Payment.create({
            "amount": {
                "value": str(total_amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "http://localhost:5173/order-success"
            },
            "capture": True,
            "description": f"Заказ №{order.id} от {request.user.email}",
            "metadata": {
                "order_id": order.id
            }
        })

        # 4. Сохраняем payment_id в заказ
        order.payment_id = payment.id
        order.save()

        # 5. Очищаем корзину ТОЛЬКО ПОСЛЕ УСПЕШНОГО СОЗДАНИЯ ПЛАТЕЖА
        cart.items.all().delete()

        # 6. Возвращаем ссылку на оплату
        return Response({
            "order_id": order.id,
            "confirmation_url": payment.confirmation.confirmation_url
        }, status=status.HTTP_201_CREATED)
