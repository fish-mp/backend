from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.core.management import call_command
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from shop.models import Cart, CartItem, Category, Order, Product
from shop.payments import mark_order_paid, mark_order_cancelled, sync_payment
from users.models import CustomUser


def provider(params, key):
    return SimpleNamespace(id='payment-' + str(params['metadata']['order_id']), status='pending',
        amount=SimpleNamespace(**params['amount']), metadata=params['metadata'],
        confirmation=SimpleNamespace(confirmation_url='https://example.com/pay'))


class ReservationTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('buyer@example.com', 'River-Planet-42!', is_email_verified=True)
        self.client.force_authenticate(self.user)
        category = Category.objects.create(name='Plants')
        self.product = Product.objects.create(name='Plant', sku='plant', category=category, price=100, stock_quantity=1)
        self.cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=self.cart, product=self.product)
        self.payload = {'email': self.user.email, 'phone': '+79991234567', 'offer_accepted': True}
        self.key = str(uuid.uuid4())
        lookup = patch('shop.payments.Payment.find_one', side_effect=lambda payment_id: provider(
            Order.objects.get(payment_id=payment_id).payment_request, 'unused'))
        lookup.start()
        self.addCleanup(lookup.stop)

    def checkout(self, **payload):
        return self.client.post('/api/orders/', {**self.payload, **payload}, format='json', HTTP_IDEMPOTENCY_KEY=self.key)

    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_reservation_retry_and_paid_event_do_not_deduct_twice(self, create):
        first = self.checkout()
        self.assertEqual(first.status_code, 201)
        order = Order.objects.get()
        from yookassa.domain.request import PaymentRequest
        PaymentRequest(order.payment_request).validate()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertTrue(order.stock_reserved)
        self.product.name = 'Changed after checkout'
        self.product.price = 200
        self.product.save()
        self.assertEqual(self.checkout().data['order_id'], order.pk)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(order.payment_request['receipt']['items'][0]['description'], 'Plant')
        self.assertTrue(mark_order_paid(order))
        self.assertFalse(mark_order_paid(order))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertFalse(CartItem.objects.filter(cart=self.cart).exists())

    @patch('shop.payments.Payment.create', side_effect=OSError('ambiguous timeout'))
    def test_timeout_retry_reuses_identical_request_and_provider_key(self, create):
        self.assertEqual(self.checkout().status_code, 502)
        order = Order.objects.get()
        original = create.call_args
        with patch('shop.payments.Payment.create', side_effect=provider) as retry:
            self.assertEqual(self.checkout().status_code, 200)
            self.assertEqual(retry.call_args, original)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.pk, Order.objects.get().pk)

    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_provider_cancellation_releases_stock_once_and_keeps_cart(self, create):
        self.checkout()
        order = Order.objects.get()
        self.assertTrue(mark_order_cancelled(order))
        self.assertFalse(mark_order_cancelled(order))
        self.assertFalse(mark_order_paid(order))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)
        self.assertTrue(self.product.is_in_stock)
        self.assertTrue(CartItem.objects.filter(cart=self.cart).exists())

    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_same_key_cannot_change_amount_or_owner_and_other_buyer_cannot_reserve_last_item(self, create):
        self.checkout()
        self.assertEqual(self.checkout(phone='+79997654321').status_code, 409)
        other = CustomUser.objects.create_user('other@example.com', 'River-Planet-42!', is_email_verified=True)
        other_cart = Cart.objects.create(user=other)
        CartItem.objects.create(cart=other_cart, product=self.product)
        self.client.force_authenticate(other)
        self.assertEqual(self.checkout().status_code, 409)
        self.key = str(uuid.uuid4())
        self.assertEqual(self.checkout().status_code, 409)
        self.assertEqual(Order.objects.count(), 1)

    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_periodic_reconciliation_confirms_missing_webhook(self, create):
        self.checkout()
        order = Order.objects.get()
        payment = provider(order.payment_request, order.payment_key)
        payment.status = 'succeeded'
        with patch('shop.payments.Payment.find_one', return_value=payment):
            call_command('reconcile_payments')
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.payment_request, {})

    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_pending_payment_is_not_released_by_local_age(self, create):
        self.checkout()
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=3))
        with patch('shop.payments.Payment.find_one', return_value=provider(order.payment_request, order.payment_key)):
            sync_payment(order)
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(self.product.stock_quantity, 0)

    @patch('shop.payments.Payment.create', side_effect=OSError('ambiguous timeout'))
    def test_expired_provider_key_is_never_replayed_and_payment_is_found_in_list(self, create):
        self.checkout()
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(payment_started_at=timezone.now() - timedelta(days=2))
        order.refresh_from_db()
        payment = provider(order.payment_request, order.payment_key)
        payment.status = 'canceled'
        with patch('shop.payments.Payment.create') as forbidden, patch('shop.payments.Payment.list', return_value=SimpleNamespace(items=[payment], next_cursor=None)):
            sync_payment(order)
            forbidden.assert_not_called()
        self.assertEqual(order.status, 'cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

    @patch('shop.payments.Payment.create', side_effect=OSError('ambiguous timeout'))
    def test_unresolved_old_payment_stays_reserved_for_manual_review(self, create):
        self.checkout()
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(payment_started_at=timezone.now() - timedelta(days=2))
        order.refresh_from_db()
        with patch('shop.payments.Payment.create') as forbidden, patch('shop.payments.Payment.list', return_value=SimpleNamespace(items=[], next_cursor=None)):
            sync_payment(order)
            forbidden.assert_not_called()
        self.assertTrue(order.payment_review_required)
        self.assertTrue(order.stock_reserved)
        self.assertEqual(order.status, 'pending')


    @patch('shop.payments.Payment.create', side_effect=provider)
    def test_provider_not_found_never_recreates_payment_or_releases_stock(self, create):
        from yookassa.domain.exceptions import NotFoundError
        self.checkout()
        order = Order.objects.get()
        with patch('shop.payments.Payment.find_one', side_effect=NotFoundError('not found')):
            sync_payment(order)
        self.assertTrue(order.payment_review_required)
        self.assertEqual(order.status, 'pending')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertEqual(create.call_count, 1)


class ConcurrentLastItemTest(TransactionTestCase):
    def test_two_parallel_buyers_cannot_buy_the_same_last_item(self):
        category = Category.objects.create(name='Plants')
        product = Product.objects.create(name='Only one', sku='one', category=category, price=100, stock_quantity=1)
        users = [CustomUser.objects.create_user(f'buyer{i}@example.com', 'River-Planet-42!', is_email_verified=True) for i in range(2)]
        for user in users:
            cart = Cart.objects.create(user=user)
            CartItem.objects.create(cart=cart, product=product)
        def buy(user):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user)
                return client.post('/api/orders/', {'email':'buyer@example.com','phone':'+79991234567','offer_accepted':True},
                    format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code
            finally:
                close_old_connections()
        with patch('shop.payments.Payment.create', side_effect=provider):
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(buy, users))
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertTrue(all(s in [201,409,503] for s in statuses), statuses)
        self.assertEqual(Order.objects.count(), 1)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)


class ProviderTransportTest(APITestCase):
    def test_sdk_transport_sets_socket_timeout_and_closes_session(self):
        from shop.payments import PaymentClient
        with patch.object(PaymentClient, 'get_session') as get_session:
            client = object.__new__(PaymentClient)
            client.endpoint = 'https://api.yookassa.ru/v3'
            session = get_session.return_value.__enter__.return_value
            client.execute({}, 'POST', '/payments', None, {})
            self.assertEqual(session.request.call_args.kwargs['timeout'], (3.05, 10))
            self.assertTrue(session.request.call_args.kwargs['verify'])
            get_session.return_value.__exit__.assert_called_once()


class OrderAdminStateTest(APITestCase):
    def test_admin_can_fulfil_but_cannot_reopen_a_paid_order(self):
        from shop.admin import OrderAdminForm
        class StatusForm(OrderAdminForm):
            class Meta(OrderAdminForm.Meta):
                fields = ['status']
        user = CustomUser.objects.create_user('admin-state@example.com','River-Planet-42!',is_email_verified=True)
        order = Order.objects.create(user=user,status='paid',payment_id='paid-id',total_amount=100)
        invalid = StatusForm({'status':'pending'},instance=order)
        self.assertFalse(invalid.is_valid())
        self.assertIn('status',invalid.errors)
        order.refresh_from_db()
        valid = StatusForm({'status':'shipped'},instance=order)
        self.assertTrue(valid.is_valid(),valid.errors)
