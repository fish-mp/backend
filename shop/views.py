from rest_framework import viewsets, status, filters, mixins, serializers
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
    CartSerializer, CartItemSerializer, OrderSerializer, CheckoutSerializer
)
from rest_framework.views import APIView
from yookassa import Configuration, Payment
from django.conf import settings
from django.db import transaction
from django.db.models import F, Avg, Prefetch, Case, When, Value, BooleanField
from decimal import Decimal
import re
import requests
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse, JsonResponse
import json
import logging

logger = logging.getLogger(__name__)


def product_queryset():
    return Product.objects.select_related('brand', 'category__parent', 'color').annotate(
        _average_rating=Avg('reviews__score')).prefetch_related('images')


def configure_yookassa():
    """Однократно настраивает реквизиты ЮKassa из настроек проекта."""
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def notify_seller_order_paid(order):
    """
    Уведомляет продавца об оплаченном заказе в Telegram.
    Ошибки не пробрасываем — сбой уведомления не должен влиять на обработку оплаты.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        lines = [
            f"🛒 Оплачен заказ №{order.id}",
            f"Сумма: {order.total_amount} ₽",
            "",
            "Товары:",
        ]
        for item in order.items.select_related('product').all():
            name = item.product.name if item.product else "удалённый товар"
            lines.append(f"• {name} × {item.quantity} — {item.price} ₽")

        address = ", ".join(filter(None, [
            order.postal_code, order.city, order.street,
            f"д. {order.house}" if order.house else "",
            f"кв. {order.apartment}" if order.apartment else "",
        ]))
        lines += ["", f"Покупатель: {order.email}", f"Телефон: {order.phone}"]
        if address:
            lines.append(f"Адрес: {address}")

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "\n".join(lines)},
            timeout=10,
        )
    except Exception:
        logger.exception("Не удалось отправить Telegram-уведомление о заказе %s", order.id)


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
            updated = Product.objects.filter(pk=item.product_id, stock_quantity__gte=item.quantity).update(
                stock_quantity=F('stock_quantity') - item.quantity,
                is_in_stock=Case(When(stock_quantity__lte=item.quantity, then=Value(False)),
                                 default=F('is_in_stock'), output_field=BooleanField()),
            )
            if not updated:
                # Payment has already succeeded: preserve that fact for support.
                # Inventory reservation before payment is still required to
                # prevent overselling across separate pending orders.
                logger.error('Paid order %s needs inventory reconciliation: product %s', locked_order.pk, item.product_id)

            cart_items = CartItem.objects.filter(cart__user=locked_order.user, product_id=item.product_id)
            cart_items.filter(quantity__lte=item.quantity).delete()
            cart_items.filter(quantity__gt=item.quantity).update(quantity=F('quantity') - item.quantity)

        locked_order.status = 'paid'
        locked_order.save(update_fields=['status'])

        # Корзину очищаем только после подтверждённой оплаты

        # Уведомляем продавца только после успешного коммита транзакции
        transaction.on_commit(lambda: notify_seller_order_paid(locked_order))
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
    queryset = Category.objects.select_related('parent').all()
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

        if not isinstance(event, dict) or not isinstance(event.get('object'), dict):
            return HttpResponse(status=400)

        event_type = event.get('event')
        payment_obj = event.get('object') or {}
        payment_id = payment_obj.get('id')

        if not isinstance(payment_id, str) or not payment_id or len(payment_id) > 100:
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
        if (Decimal(str(payment.amount.value)) != order.total_amount
                or payment.amount.currency != 'RUB'
                or str((payment.metadata or {}).get('order_id')) != str(order.pk)
                or str(payment.id) != payment_id):
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
    queryset = product_queryset().filter(is_available=True)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'name']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Collection.objects.prefetch_related(Prefetch('products', queryset=product_queryset().filter(is_available=True))).all()
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
        return Favorite.objects.filter(user=self.request.user).prefetch_related(Prefetch('product', queryset=product_queryset()))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class CartViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user).prefetch_related(
            Prefetch('items', queryset=CartItem.objects.prefetch_related(Prefetch('product', queryset=product_queryset()))))

    def list(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(self.get_queryset().get(pk=cart.pk))
        return Response(serializer.data)

class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user).prefetch_related(
            Prefetch('product', queryset=product_queryset()))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart, _ = Cart.objects.get_or_create(user=request.user)
        # Serialize additions to the same cart; the DB constraint also protects
        # against duplicate positions created outside this endpoint.
        Cart.objects.select_for_update().get(pk=cart.pk)
        product = serializer.validated_data['product']
        quantity = serializer.validated_data.get('quantity', 1)
        existing = CartItem.objects.filter(cart=cart, product=product).first()
        total_quantity = quantity + (existing.quantity if existing else 0)
        if total_quantity > product.stock_quantity or total_quantity > 10000:
            raise serializers.ValidationError({'quantity': 'Недостаточно товара на складе.'})
        if existing:
            existing.quantity = total_quantity
            existing.save(update_fields=['quantity'])
            item = existing
        else:
            item = serializer.save(cart=cart)
        return Response(self.get_serializer(item).data, status=200 if existing else 201)

class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items__product')

    def create(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = list(cart.items.select_related('product').all())
        if not cart_items:
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        checkout = CheckoutSerializer(data=request.data)
        checkout.is_valid(raise_exception=True)
        data = checkout.validated_data
        email, phone = data['email'], data['phone']
        city, street, house = data['city'], data['street'], data['house']
        apartment, postal_code = data['apartment'], data['postal_code']
        offer_accepted = data['offer_accepted']
        delivery_method, beyond_mkad = data['delivery_method'], data['beyond_mkad']

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
        items_total = sum(item.product.price * item.quantity for item in cart_items)
        delivery_cost = Decimal('0')
        # Доставка бесплатна при заказе от 10 000 ₽; иначе 1500 ₽ (в МКАД) или 3000 ₽ (за МКАД)
        if delivery_method == 'delivery' and items_total < Decimal('10000'):
            delivery_cost = Decimal('3000') if beyond_mkad else Decimal('1500')
        total_amount = (items_total + delivery_cost).quantize(Decimal('0.01'))

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
        # Доставка — отдельная позиция чека, иначе сумма позиций не сойдётся с amount
        if delivery_cost > 0:
            receipt_items.append({
                "description": "Доставка",
                "quantity": "1",
                "amount": {
                    "value": str(delivery_cost),
                    "currency": "RUB",
                },
                "vat_code": settings.YOOKASSA_VAT_CODE,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            })
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
            # A timeout may happen after the provider accepted the payment.
            # Preserve the order for reconciliation instead of losing its items.
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
