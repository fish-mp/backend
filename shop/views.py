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
from django.conf import settings
from django.db import transaction, OperationalError
from django.utils import timezone
import hashlib
import uuid
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

        lines += ["", f"Открыть заказ: {settings.FRONTEND_URL}/admin/shop/order/{order.pk}/change/"]

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "\n".join(lines)},
            timeout=10,
        )
    except Exception:
        logger.exception("Не удалось отправить Telegram-уведомление о заказе %s", order.id)


from shop.payments import (Payment, configure_yookassa, mark_order_paid, sync_payment,
                           apply_payment, reserve_items, PaymentMismatch)
from users.throttles import AuthRateThrottle
from legal.catalog import record_consent


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

        try:
            apply_payment(order, payment)
        except PaymentMismatch:
            Order.objects.filter(pk=order.pk).update(payment_review_required=True)
            logger.error("Provider identity mismatch for order %s", order.pk)
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

    def payment_response(self, order, created=False):
        try:
            sync_payment(order)
        except Exception as exc:
            # No request payload, email, address or provider credentials in logs.
            logger.warning("Payment check failed for order %s (%s)", order.pk, type(exc).__name__)
            return Response({'error': 'Платёж проверяется. Не создавайте новый заказ — повторите проверку этого заказа.',
                             'order_id': order.pk, 'status': 'pending'}, status=502)
        return Response({'order_id': order.pk, 'status': order.status,
                         'payment_review_required': order.payment_review_required,
                         'confirmation_url': order.confirmation_url if order.status == 'pending' and not order.payment_review_required else None},
                        status=201 if created else 200)

    @action(detail=True, methods=['post'], throttle_classes=[AuthRateThrottle])
    def payment(self, request, pk=None):
        return self.payment_response(self.get_object())

    def create(self, request, *args, **kwargs):
        try:
            return self._create_checkout(request)
        except OperationalError as exc:
            if 'locked' not in str(exc).lower():
                raise
            return Response({'error': 'Заказ обрабатывается параллельно. Повторите запрос с тем же ключом.'}, status=503)

    def _create_checkout(self, request):
        checkout = CheckoutSerializer(data=request.data)
        checkout.is_valid(raise_exception=True)
        data = checkout.validated_data
        raw_key = request.headers.get('Idempotency-Key')
        try:
            checkout_key = uuid.UUID(raw_key) if raw_key else uuid.uuid4()
        except (ValueError, TypeError, AttributeError):
            raise serializers.ValidationError({'detail': 'Некорректный Idempotency-Key.'})
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        cart, _ = Cart.objects.get_or_create(user=request.user)
        with transaction.atomic():
            # First statement is a write: serializes this cart on PostgreSQL
            # and obtains SQLite's writer lock before reading the snapshot.
            Cart.objects.filter(pk=cart.pk).update(created_at=F('created_at'))
            existing = Order.objects.filter(checkout_key=checkout_key).first()
            if existing:
                if existing.user_id != request.user.pk or existing.checkout_fingerprint != fingerprint:
                    return Response({'error': 'Ключ уже использован для другого оформления.'}, status=409)
                order = existing
                created = False
            else:
                pending = Order.objects.filter(user=request.user, status='pending', stock_reserved=True).first()
                if pending:
                    return Response({'error': 'У вас уже есть неоплаченный заказ. Продолжите его оплату.',
                                     'order_id': pending.pk}, status=409)
                cart_items = list(cart.items.select_related('product').order_by('product_id'))
                if not cart_items:
                    return Response({'error': 'Корзина пуста'}, status=400)
                reserve_items(cart_items)
                items_total = sum(item.product.price * item.quantity for item in cart_items)
                delivery_cost = Decimal('0')
                if data['delivery_method'] == 'delivery' and items_total < Decimal('10000'):
                    delivery_cost = Decimal('3000') if data['beyond_mkad'] else Decimal('1500')
                order = Order.objects.create(
                    user=request.user, status='pending', checkout_key=checkout_key,
                    checkout_fingerprint=fingerprint, payment_key=uuid.uuid4(),
                    payment_started_at=timezone.now(), stock_reserved=True,
                    delivery_method=data['delivery_method'], beyond_mkad=data['beyond_mkad'], delivery_cost=delivery_cost,
                    total_amount=(items_total + delivery_cost).quantize(Decimal('0.01')),
                    **{name: data[name] for name in ['email','phone','city','street','house','apartment','postal_code','offer_accepted']})
                OrderItem.objects.bulk_create([
                    OrderItem(order=order, product=item.product, product_name=item.product.name,
                              price=item.product.price, quantity=item.quantity) for item in cart_items])
                receipt_items = [{
                    'description': item.product.name[:128], 'quantity': str(item.quantity),
                    'amount': {'value': str(item.product.price), 'currency': 'RUB'},
                    'vat_code': settings.YOOKASSA_VAT_CODE, 'payment_subject': 'commodity',
                    'payment_mode': 'full_payment'} for item in cart_items]
                if delivery_cost:
                    receipt_items.append({'description': 'Доставка', 'quantity': '1',
                        'amount': {'value': str(delivery_cost), 'currency': 'RUB'},
                        'vat_code': settings.YOOKASSA_VAT_CODE, 'payment_subject': 'service',
                        'payment_mode': 'full_payment'})
                customer = {'email': data['email'], 'phone': re.sub(r'\D', '', data['phone'])}
                order.payment_request = {
                    'amount': {'value': str(order.total_amount), 'currency': 'RUB'},
                    'confirmation': {'type': 'redirect', 'return_url': settings.FRONTEND_URL + '/order-success'},
                    'capture': True, 'description': f'Заказ №{order.pk}',
                    'receipt': {'customer': customer, 'items': receipt_items},
                    'metadata': {'order_id': str(order.pk), 'source': 'fishkids-shop', 'checkout_key': str(order.checkout_key)}}
                order.save(update_fields=['payment_request'])
                record_consent(request.user, 'checkout', data.get('privacy_consent'), order.pk)
                created = True
        return self.payment_response(order, created)
