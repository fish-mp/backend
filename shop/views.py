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
from django.db import transaction
from django.db.models import F
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse, JsonResponse
import json
import logging

logger = logging.getLogger(__name__)


def configure_yookassa():
    """Однократно настраивает реквизиты ЮKassa из настроек проекта."""
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def mark_order_paid(order):
    """
    Идемпотентно переводит заказ в статус 'paid', списывает остатки со склада
    и очищает корзину пользователя. Безопасно вызывать повторно: при повторном
    вызове заказ уже не в статусе 'pending', поэтому ничего не произойдёт.
    """
    with transaction.atomic():
        # Блокируем заказ, чтобы параллельные вызовы вебхука не списали склад дважды
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != 'pending':
            return False

        for item in locked_order.items.select_related('product').all():
            if item.product is None:
                continue
            # Атомарное списание остатка на уровне БД
            Product.objects.filter(pk=item.product.pk).update(
                stock_quantity=F('stock_quantity') - item.quantity
            )
            product = Product.objects.get(pk=item.product.pk)
            if product.stock_quantity <= 0:
                product.stock_quantity = max(product.stock_quantity, 0)
                product.is_in_stock = False
                product.save(update_fields=['stock_quantity', 'is_in_stock'])

        locked_order.status = 'paid'
        locked_order.save(update_fields=['status'])

        # Корзину очищаем только после подтверждённой оплаты
        CartItem.objects.filter(cart__user=locked_order.user).delete()
    return True


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
        except (ValueError, TypeError):
            logger.warning("YooKassa webhook: невалидный JSON")
            return HttpResponse(status=400)

        event_type = event.get('event')
        payment_obj = event.get('object') or {}
        payment_id = payment_obj.get('id')

        if not payment_id:
            return HttpResponse(status=200)

        order = Order.objects.filter(payment_id=payment_id).first()
        if order is None:
            # Платёж не относится к нашим заказам — игнорируем
            return HttpResponse(status=200)

        # Не доверяем телу вебхука: подтверждаем статус напрямую у ЮKassa.
        try:
            configure_yookassa()
            payment = Payment.find_one(payment_id)
        except Exception:
            logger.exception("YooKassa webhook: не удалось проверить платёж %s", payment_id)
            # 500 -> ЮKassa повторит доставку позже
            return HttpResponse(status=500)

        # Сверяем сумму, чтобы исключить подмену
        if str(payment.amount.value) != str(order.total_amount):
            logger.error(
                "YooKassa webhook: сумма платежа %s не совпадает с заказом %s",
                payment_id, order.id,
            )
            return HttpResponse(status=200)

        if event_type == 'payment.succeeded' and payment.status == 'succeeded':
            mark_order_paid(order)
        elif event_type == 'payment.canceled' and payment.status == 'canceled':
            Order.objects.filter(pk=order.pk, status='pending').update(status='cancelled')

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
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = list(cart.items.select_related('product').all())
        if not cart_items:
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        # 0. Контактные данные, адрес доставки и согласие с офертой
        data = request.data
        email = (data.get('email') or '').strip()
        phone = (data.get('phone') or '').strip()
        city = (data.get('city') or '').strip()
        street = (data.get('street') or '').strip()
        house = (data.get('house') or '').strip()
        apartment = (data.get('apartment') or '').strip()
        postal_code = (data.get('postal_code') or '').strip()
        offer_accepted = bool(data.get('offer_accepted'))
        delivery_method = (data.get('delivery_method') or 'pickup').strip()
        beyond_mkad = bool(data.get('beyond_mkad'))

        required = {
            'email': email, 'phone': phone,
            'city': city, 'street': street, 'house': house,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            return Response(
                {"error": "Заполните обязательные поля", "fields": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "Некорректный email", "fields": ["email"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not offer_accepted:
            return Response(
                {"error": "Необходимо согласие с публичной офертой", "fields": ["offer_accepted"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Проверяем доступность и остатки до создания заказа
        for item in cart_items:
            product = item.product
            if not product.is_available:
                return Response(
                    {"error": f"Товар «{product.name}» недоступен для заказа"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if product.stock_quantity < item.quantity:
                return Response(
                    {"error": f"Недостаточно товара «{product.name}» на складе"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        total_amount = sum(item.product.price * item.quantity for item in cart_items)
        if delivery_method == 'delivery':
            total_amount += 1000 if beyond_mkad else 300

        # 2. Создаём заказ и позиции атомарно: при сбое не останется «висячих» записей
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                status='pending',
                total_amount=total_amount,
                email=email,
                phone=phone,
                city=city,
                street=street,
                house=house,
                apartment=apartment,
                postal_code=postal_code,
                offer_accepted=offer_accepted,
            )
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    product=item.product,
                    price=item.product.price,
                    quantity=item.quantity,
                )
                for item in cart_items
            ])

        # 3. Создаём платёж в ЮKassa (с чеком по 54-ФЗ)
        configure_yookassa()
        receipt_items = [
            {
                "description": item.product.name[:128],
                "quantity": str(item.quantity),
                "amount": {
                    "value": str(item.product.price),
                    "currency": "RUB",
                },
                "vat_code": settings.YOOKASSA_VAT_CODE,
                "payment_subject": "commodity",
                "payment_mode": "full_payment",
            }
            for item in cart_items
        ]
        # Покупатель в чеке: email обязателен, телефон — в формате только цифр (E.164)
        receipt_customer = {"email": email}
        phone_digits = re.sub(r'\D', '', phone)
        if phone_digits:
            receipt_customer["phone"] = phone_digits

        try:
            payment = Payment.create({
                "amount": {
                    "value": str(total_amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://fishkids.ru/order-success"
                },
                "capture": True,
                "description": f"Заказ №{order.id} от {request.user.email}",
                "receipt": {
                    "customer": receipt_customer,
                    "items": receipt_items,
                },
                "metadata": {
                    "order_id": order.id
                }
            })
        except Exception:
            logger.exception("Не удалось создать платёж ЮKassa для заказа %s", order.id)
            # Откатываем заказ, чтобы не копить непроведённые «pending»
            order.delete()
            return Response(
                {"error": "Не удалось создать платёж. Попробуйте позже."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # 4. Сохраняем payment_id в заказ
        order.payment_id = payment.id
        order.save(update_fields=['payment_id'])

        # Корзина и остатки очищаются/списываются ТОЛЬКО после подтверждения
        # оплаты в YooKassaWebhookView — чтобы не терять товары при незавершённой оплате.

        # 5. Возвращаем ссылку на оплату
        return Response({
            "order_id": order.id,
            "confirmation_url": payment.confirmation.confirmation_url
        }, status=status.HTTP_201_CREATED)
