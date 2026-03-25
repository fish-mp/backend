import uuid
from django.db import models
from django.conf import settings
from django.db.models import Avg

class Brand(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    image = models.ImageField(upload_to='brands/', blank=True, null=True, verbose_name="Логотип")
    contacts = models.TextField(blank=True, verbose_name="Контакты")
    website = models.URLField(blank=True, verbose_name="Сайт")

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренды"

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=150, verbose_name="Название категории")
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, 
        related_name='subcategories', verbose_name="Родительская категория"
    )
    
    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} -> {self.name}"
        return self.name
    
class Color(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, blank=True, verbose_name="Название цвета")

    class Meta:
        verbose_name = "Цвет товара"
        verbose_name_plural = "Цвета товаров"

    def __str__(self):
        return self.name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name="Название")
    sku = models.CharField(max_length=50, unique=True, verbose_name="Артикул")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products', verbose_name="Категория")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name="Бренд")
    
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    short_description = models.CharField(max_length=255, blank=True, verbose_name="Краткое описание")
    description = models.TextField(blank=True, verbose_name="Полное описание")
    
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="Количество на складе")
    is_in_stock = models.BooleanField(default=True, verbose_name="В наличии")
    is_available = models.BooleanField(default=True, verbose_name="Доступен для заказа (Активен)")
    
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Вес (кг)")
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Цвет")
    length = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Длина (см)")
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Ширина (см)")
    height = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Высота (см)")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self):
        return self.name

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(Avg('score'))['score__avg']
        return round(avg, 1) if avg else 0.0

class ProductImage(models.Model):
    """
    Отдельная таблица для картинок товара. 
    Позволяет привязать несколько фото к одному товару.
    P.S. Если решишь использовать общую таблицу файлов (как ты упоминал), 
    просто замени ImageField на ForeignKey к твоей модели файлов.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/', verbose_name="Изображение")
    is_main = models.BooleanField(default=False, verbose_name="Главное фото")

    class Meta:
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"

class Collection(models.Model):
    name = models.CharField(max_length=150, verbose_name="Название подборки")
    cover_image = models.ImageField(upload_to='collections/', blank=True, null=True, verbose_name="Обложка")
    products = models.ManyToManyField(Product, related_name='collections', verbose_name="Товары")

    class Meta:
        verbose_name = "Подборка/Каталог"
        verbose_name_plural = "Подборки/Каталоги"

    def __str__(self):
        return self.name

class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews', verbose_name="Товар")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews', verbose_name="Пользователь")
    score = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)], verbose_name="Оценка")
    text = models.TextField(blank=True, verbose_name="Отзыв")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        unique_together = ('product', 'user')

class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
        related_name='favorites', verbose_name="Пользователь"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, 
        related_name='favorited_by', verbose_name="Товар"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Избранный товар"
        verbose_name_plural = "Избранные товары"
        # Один пользователь может добавить конкретный товар в избранное только один раз
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.product.name} (Избранное: {self.user.email})"


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
        related_name='cart', verbose_name="Пользователь"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"

    def __str__(self):
        return f"Корзина пользователя {self.user.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, 
        related_name='items', verbose_name="Корзина"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, 
        verbose_name="Товар"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Товар в корзине"
        verbose_name_plural = "Товары в корзине"

    def __str__(self):
        return f"{self.product.name} ({self.quantity} шт.)"


class Order(models.Model):
    STATUS_CHOICES = (
        ('new', 'Новый'),
        ('processing', 'В обработке'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменен'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
        related_name='orders', verbose_name="Пользователь"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, 
        default='new', verbose_name="Статус"
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, 
        verbose_name="Общая сумма"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self):
        return f"Заказ №{self.id} от {self.user.email}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, 
        related_name='items', verbose_name="Заказ"
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, 
        null=True, verbose_name="Товар"
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, 
        verbose_name="Цена на момент покупки"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Товар в заказе"
        verbose_name_plural = "Товары в заказе"

    def __str__(self):
        product_name = self.product.name if self.product else "Удаленный товар"
        return f"{product_name} ({self.quantity} шт.)"