"""Stock reservations and provider reconciliation. Network calls never hold DB locks."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Case, When, Value, BooleanField
from django.utils import timezone
from rest_framework.exceptions import APIException
from yookassa import Configuration, Payment as SDKPayment
from yookassa.client import ApiClient
from yookassa.domain.exceptions import NotFoundError

from shop.models import CartItem, Order, Product

logger = logging.getLogger(__name__)


class PaymentClient(ApiClient):
    def execute(self, body, method, path, query_params, request_headers):
        # The upstream SDK otherwise makes socket requests without a timeout.
        # Keep its validation/auth/error handling, but do not log receipt PII.
        with self.get_session() as session:
            return session.request(method, self.endpoint + path, params=query_params,
                headers=request_headers, json=body, verify=True, timeout=(3.05, 10))


class Payment(SDKPayment):
    def __init__(self):
        self.client = PaymentClient()


class StockUnavailable(APIException):
    status_code = 409
    default_detail = 'Недостаточно свободного товара. Обновите корзину.'


class PaymentMismatch(Exception):
    pass


def configure_yookassa():
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
    Configuration.max_attempts = 1


def reserve_items(items):
    # Conditional UPDATE is atomic on both SQLite and PostgreSQL. Stable ordering
    # also avoids taking product locks in opposite orders on PostgreSQL.
    for item in sorted(items, key=lambda i: str(i.product_id)):
        if not item.product_id or not Product.objects.filter(
                pk=item.product_id, is_available=True, is_in_stock=True,
                stock_quantity__gte=item.quantity).update(
                    stock_quantity=F('stock_quantity') - item.quantity,
                    is_in_stock=Case(When(stock_quantity=item.quantity, then=Value(False)),
                                     default=F('is_in_stock'), output_field=BooleanField())):
            raise StockUnavailable()


@transaction.atomic
def mark_order_paid(order):
    # Make the first statement a write: SQLite cannot upgrade a competing
    # read transaction reliably. The status comparison claims this event once.
    if not Order.objects.filter(pk=order.pk, status='pending').update(status='paid'):
        return False
    locked = Order.objects.get(pk=order.pk)
    needs_review = locked.payment_review_required
    for item in locked.items.select_related('product').all():
        if item.product_id and not locked.stock_reserved:
            # Compatibility with payments created before reservations existed.
            updated = Product.objects.filter(pk=item.product_id, stock_quantity__gte=item.quantity).update(
                stock_quantity=F('stock_quantity') - item.quantity,
                is_in_stock=Case(When(stock_quantity__lte=item.quantity, then=Value(False)),
                                 default=F('is_in_stock'), output_field=BooleanField()))
            if not updated:
                needs_review = True
                logger.error('Paid legacy order %s needs stock reconciliation', locked.pk)
        cart_items = CartItem.objects.filter(cart__user=locked.user, product_id=item.product_id)
        cart_items.filter(quantity__lte=item.quantity).delete()
        cart_items.filter(quantity__gt=item.quantity).update(quantity=F('quantity') - item.quantity)
    Order.objects.filter(pk=locked.pk).update(
        stock_reserved=False, payment_request={}, payment_review_required=needs_review)
    from shop.views import notify_seller_order_paid
    transaction.on_commit(lambda: notify_seller_order_paid(locked))
    return True


@transaction.atomic
def mark_order_cancelled(order):
    if not Order.objects.filter(pk=order.pk, status='pending').update(status='cancelled'):
        return False
    locked = Order.objects.get(pk=order.pk)
    if locked.stock_reserved:
        for item in locked.items.order_by('product_id'):
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock_quantity=F('stock_quantity') + item.quantity, is_in_stock=True)
    Order.objects.filter(pk=locked.pk).update(
        stock_reserved=False, payment_request={}, confirmation_url='')
    return True


def validate_payment(order, payment):
    try:
        valid = (str(payment.id) and len(str(payment.id)) <= 100
                 and Decimal(str(payment.amount.value)) == order.total_amount
                 and payment.amount.currency == 'RUB'
                 and str((payment.metadata or {}).get('order_id')) == str(order.pk)
                 and (not order.payment_id or order.payment_id == str(payment.id))
                 and (not order.payment_key or (str((payment.metadata or {}).get('checkout_key')) == str(order.checkout_key)
                                               and (payment.metadata or {}).get('source') == 'fishkids-shop')))
    except (AttributeError, TypeError, InvalidOperation):
        valid = False
    if not valid:
        Order.objects.filter(pk=order.pk).update(payment_review_required=True)
        raise PaymentMismatch('Provider payment does not match order')


@transaction.atomic
def apply_payment(order, payment):
    # Acquire a write lock before reading or changing payment identity.
    Order.objects.filter(pk=order.pk).update(payment_last_checked_at=timezone.now())
    locked = Order.objects.get(pk=order.pk)
    validate_payment(locked, payment)
    if locked.payment_id and locked.payment_id != str(payment.id):
        raise PaymentMismatch('Payment identity changed')
    url = getattr(getattr(payment, 'confirmation', None), 'confirmation_url', '') or ''
    updates = {'payment_id': str(payment.id), 'payment_review_required': False}
    if url:
        updates['confirmation_url'] = url
    Order.objects.filter(pk=locked.pk).update(**updates)
    locked.payment_id = str(payment.id)
    if payment.status == 'succeeded':
        mark_order_paid(locked)
    elif payment.status == 'canceled':
        mark_order_cancelled(locked)
    elif payment.status in ('pending', 'waiting_for_capture') and locked.status == 'pending' and not locked.stock_reserved:
        # Reserve old, still-payable orders during the first reconciliation.
        try:
            with transaction.atomic():
                reserve_items(list(locked.items.all()))
                Order.objects.filter(pk=locked.pk).update(stock_reserved=True)
        except StockUnavailable:
            Order.objects.filter(pk=locked.pk).update(payment_review_required=True)
            logger.error('Legacy pending order %s needs stock reconciliation', locked.pk)
    order.refresh_from_db()
    return order


def recover_old_unknown_payment(order):
    # YooKassa forgets idempotency keys after 24 hours. Never POST again after
    # that window: search the original interval instead of risking a new charge.
    started = order.payment_started_at or order.created_at
    start = started - timedelta(minutes=5)
    end = started + timedelta(hours=24)
    params = {'created_at.gte': start.isoformat(), 'created_at.lte': end.isoformat(), 'limit': 100}
    found = []
    for _ in range(10):
        page = Payment.list(params)
        matches = [p for p in page.items if str((p.metadata or {}).get('order_id')) == str(order.pk)]
        found.extend(matches)
        if len(found) > 1:
            break
        cursor = getattr(page, 'next_cursor', None)
        if not cursor:
            if len(found) == 1:
                return found[0]
            break
        params['cursor'] = cursor
    Order.objects.filter(pk=order.pk).update(payment_review_required=True)
    return None


def sync_payment(order):
    if order.status != 'pending':
        return order
    configure_yookassa()
    if order.payment_id:
        try:
            payment = Payment.find_one(order.payment_id)
        except NotFoundError:
            Order.objects.filter(pk=order.pk).update(payment_review_required=True)
            order.refresh_from_db()
            return order
    elif order.payment_key and order.payment_request and order.payment_started_at:
        if timezone.now() - order.payment_started_at < timedelta(hours=23):
            payment = Payment.create(order.payment_request, str(order.payment_key))
        else:
            payment = recover_old_unknown_payment(order)
            if payment is None:
                order.refresh_from_db()
                return order
    else:
        # Historical requests may be searched, but must never be recreated.
        payment = recover_old_unknown_payment(order)
        if payment is None:
            order.refresh_from_db()
            return order
    try:
        return apply_payment(order, payment)
    except PaymentMismatch:
        Order.objects.filter(pk=order.pk).update(payment_review_required=True)
        raise
