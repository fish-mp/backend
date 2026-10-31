import logging
from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone
from shop.models import Order
from shop.payments import sync_payment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reconcile pending payments with YooKassa; never release stock by a local timeout.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        checked = failed = 0
        orders = Order.objects.filter(status='pending').order_by(
            F('payment_last_checked_at').asc(nulls_first=True), 'pk')[:max(1, min(options['limit'], 500))]
        for order in orders:
            Order.objects.filter(pk=order.pk).update(payment_last_checked_at=timezone.now())
            try:
                sync_payment(order)
                checked += 1
            except Exception as exc:
                failed += 1
                logger.warning('Payment reconciliation failed for order %s (%s)', order.pk, type(exc).__name__)
        self.stdout.write(f'Checked: {checked}; failed: {failed}')
