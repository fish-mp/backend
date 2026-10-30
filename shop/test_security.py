from unittest.mock import patch
from types import SimpleNamespace
import uuid

from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from shop.models import Cart, CartItem, Category, Favorite, Order, Product, Review
from shop.models import OrderItem
from shop.views import mark_order_paid
from users.models import CustomUser


class ShopSecurityTests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser('admin@example.com', 'Admin-Planet-42!')
        self.customer = CustomUser.objects.create_user('customer@example.com', 'River-Planet-42!', is_email_verified=True)
        self.category = Category.objects.create(name='Растения')
        self.product = Product.objects.create(name='Анубиас', sku='p1', category=self.category, price=100, stock_quantity=10)
        self.cart = Cart.objects.create(user=self.admin)
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        self.favorite = Favorite.objects.create(user=self.admin, product=self.product)
        self.order = Order.objects.create(user=self.admin, status='pending', total_amount=200)
        self.client.force_authenticate(self.customer)

    def test_personal_data_is_isolated_including_admin_cart(self):
        self.assertEqual(self.client.get('/api/cart/').data['items'], [])
        self.assertEqual(self.client.get('/api/favorites/').data, [])
        self.assertEqual(self.client.get('/api/orders/').data, [])
        self.assertEqual(self.client.patch(f'/api/cart-items/{self.item.pk}/', {'quantity': 1}).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/favorites/{self.favorite.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/').status_code, 404)
        self.client.post('/api/cart-items/', {'product_id': str(self.product.pk), 'quantity': 1})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 2)

    def test_order_status_cannot_be_changed_or_deleted(self):
        self.client.force_authenticate(self.admin)
        for method in ['patch', 'put', 'delete']:
            response = getattr(self.client, method)(f'/api/orders/{self.order.pk}/', {'status': 'paid'}, format='json')
            self.assertEqual(response.status_code, 405)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_cart_rejects_bad_product_quantity_and_total_over_stock(self):
        for quantity in [0, -1, 11, 10001, 'abc']:
            self.assertEqual(self.client.post('/api/cart-items/', {'product_id': str(self.product.pk), 'quantity': quantity}).status_code, 400)
        self.assertEqual(self.client.post('/api/cart-items/', {'product_id': str(uuid.uuid4()), 'quantity': 1}).status_code, 400)
        self.assertEqual(self.client.post('/api/cart-items/', {'product_id': str(self.product.pk), 'quantity': 6}).status_code, 201)
        self.assertEqual(self.client.post('/api/cart-items/', {'product_id': str(self.product.pk), 'quantity': 5}).status_code, 400)

    def test_cart_constraints_prevent_duplicate_or_zero_positions(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.filter(pk=self.item.pk).update(quantity=0)

    def test_checkout_validates_types_without_creating_payments(self):
        self.client.force_authenticate(self.admin)
        with patch('shop.views.Payment.create') as payment:
            for payload in [{'email': [], 'phone': {}}, {'email': 'buyer@example.com', 'phone': '+79991234567', 'offer_accepted': False},
                            {'email': 'buyer@example.com', 'phone': '+79991234567', 'offer_accepted': True, 'delivery_method': 'free_shipping'}]:
                self.assertEqual(self.client.post('/api/orders/', payload, format='json').status_code, 400)
            payment.assert_not_called()

    def test_product_query_count_does_not_grow_per_product(self):
        self.client.force_authenticate(None)
        with self.assertNumQueries(2):
            response = self.client.get('/api/products/')
        self.assertEqual(response.status_code, 200)
        for n in range(8):
            Product.objects.create(name=f'Товар {n}', sku=f'other{n}', category=self.category, price=20)
        with self.assertNumQueries(2):
            response = self.client.get('/api/products/')
        self.assertEqual(len(response.data), 9)

    def test_public_review_does_not_expose_email(self):
        Review.objects.create(user=self.customer, product=self.product, score=5)
        self.client.force_authenticate(None)
        self.assertNotIn(self.customer.email, str(self.client.get('/api/reviews/').data))

    def test_payment_is_idempotent_and_preserves_new_cart_items(self):
        OrderItem.objects.create(order=self.order, product=self.product, price=100, quantity=1)
        other = Product.objects.create(name='Новый товар', sku='new', category=self.category, price=50, stock_quantity=5)
        CartItem.objects.create(cart=self.cart, product=other, quantity=1)
        self.assertTrue(mark_order_paid(self.order))
        self.assertFalse(mark_order_paid(self.order))
        self.product.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 9)
        self.assertEqual(self.item.quantity, 1)
        self.assertTrue(CartItem.objects.filter(cart=self.cart, product=other).exists())

    def test_webhook_requires_provider_confirmation_and_order_identity(self):
        self.order.payment_id = 'payment-id'
        self.order.save()
        self.client.force_authenticate(None)
        provider = SimpleNamespace(id='payment-id', status='pending', amount=SimpleNamespace(value='200.00', currency='RUB'), metadata={'order_id': self.order.pk})
        with patch('shop.views.Payment.find_one', return_value=provider):
            self.assertEqual(self.client.post('/api/yookassa-webhook/', {'event': 'payment.succeeded', 'object': {'id': 'payment-id'}}, format='json').status_code, 200)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, 'pending')
            provider.status = 'succeeded'
            provider.amount.currency = 'USD'
            self.client.post('/api/yookassa-webhook/', {'event': 'payment.succeeded', 'object': {'id': 'payment-id'}}, format='json')
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, 'pending')
            provider.amount.currency = 'RUB'
            self.client.post('/api/yookassa-webhook/', {'event': 'payment.succeeded', 'object': {'id': 'payment-id'}}, format='json')
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, 'paid')
        self.assertEqual(self.client.post('/api/yookassa-webhook/', [], format='json').status_code, 400)

    def test_ambiguous_payment_failure_preserves_order_for_reconciliation(self):
        self.client.force_authenticate(self.admin)
        before = Order.objects.count()
        with patch('shop.views.Payment.create', side_effect=OSError('provider timeout')):
            response = self.client.post('/api/orders/', {'email': self.admin.email, 'phone': '+79991234567', 'offer_accepted': True}, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(Order.objects.count(), before + 1)
        self.assertEqual(Order.objects.latest('pk').status, 'pending')
        self.assertTrue(CartItem.objects.filter(pk=self.item.pk).exists())
