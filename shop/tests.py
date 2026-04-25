from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from shop.models import (
    Category, Brand, Color, Product, 
    Cart, CartItem, Order, OrderItem, Favorite, Review
)

User = get_user_model()

class ShopAPITestCase(APITestCase):
    def setUp(self):
        """
        Метод setUp запускается перед каждым тестом.
        Здесь мы создаем тестовые данные: пользователя и товары.
        """
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            email='test@example.com', 
            password='testpassword123'
        )
        
        # Создаем базовые объекты для товара
        self.category = Category.objects.create(name='Электроника')
        self.brand = Brand.objects.create(name='Samsung')
        self.color = Color.objects.create(name='Черный')
        
        # Создаем товар
        self.product = Product.objects.create(
            name='Смартфон Galaxy S23',
            sku='SAMSUNG-S23-BLK',
            category=self.category,
            brand=self.brand,
            color=self.color,
            price=Decimal('80000.00'),
            stock_quantity=10,
        )

    def test_get_products_list_unauthenticated(self):
        """Проверка: неавторизованный пользователь может смотреть список товаров"""
        url = reverse('products-list') # Имя генерируется роутером
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что созданный товар есть в выдаче
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Смартфон Galaxy S23')

    def test_add_to_cart_and_increment_quantity(self):
        """Проверка: добавление в корзину и увеличение количества при дубле"""
        self.client.force_authenticate(user=self.user)
        
        # Создаем пустую корзину перед запросами
        Cart.objects.create(user=self.user) 
        
        url = reverse('cart-item-list')
        
        # Меняем 'product' на 'product_id'
        data_1 = {'product_id': self.product.id, 'quantity': 2}
        response_1 = self.client.post(url, data_1)
        
        self.assertEqual(response_1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CartItem.objects.count(), 1)
        
        # Меняем 'product' на 'product_id'
        data_2 = {'product_id': self.product.id, 'quantity': 3}
        response_2 = self.client.post(url, data_2)
        
        self.assertEqual(response_2.status_code, status.HTTP_200_OK) 
        self.assertEqual(CartItem.objects.count(), 1) 
        
        cart_item = CartItem.objects.first()
        self.assertEqual(cart_item.quantity, 5)

    def test_add_to_favorites(self):
        """Проверка добавления в избранное"""
        self.client.force_authenticate(user=self.user)
        url = reverse('favorites-list')
        
        # Меняем 'product' на 'product_id'
        response = self.client.post(url, {'product_id': self.product.id})
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Favorite.objects.filter(user=self.user, product=self.product).count(), 1)

    def test_create_order_from_cart(self):
        """Проверка: создание заказа из корзины и ее последующая очистка"""
        self.client.force_authenticate(user=self.user)
        
        # Создаем корзину и кладем туда товар напрямую через ORM для скорости
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        
        url = reverse('orders-list')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Проверяем, что заказ создался корректно
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, 'new')
        # 2 шт * 80 000 = 160 000
        self.assertEqual(order.total_amount, Decimal('160000.00')) 
        
        # Проверяем, что элементы заказа создались
        self.assertEqual(OrderItem.objects.count(), 1)
        order_item = OrderItem.objects.first()
        self.assertEqual(order_item.product, self.product)
        self.assertEqual(order_item.quantity, 2)
        
        # Проверяем, что корзина очистилась
        self.assertEqual(cart.items.count(), 0)

    def test_create_order_empty_cart_fails(self):
        """Проверка: нельзя создать заказ с пустой корзиной"""
        self.client.force_authenticate(user=self.user)
        Cart.objects.create(user=self.user) # Пустая корзина
        
        url = reverse('orders-list')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Корзина пуста")
        self.assertEqual(Order.objects.count(), 0)
