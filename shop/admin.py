from django.contrib import admin
from django import forms
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Category, Brand, Color, Product, ProductImage, 
    Collection, Review, Order, OrderItem,
    Cart, CartItem, Favorite 
)

class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1

class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'product_name', 'price', 'quantity')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    fields = ('product', 'quantity')



@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('name', 'sku', 'price', 'stock_quantity', 'is_in_stock', 'category')
    list_filter = ('category', 'brand', 'is_in_stock', 'is_available')
    search_fields = ('name', 'sku')
    inlines =[ProductImageInline]
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'sku', 'category', 'brand', 'price', 'short_description', 'description')
        }),
        ('Наличие и статус', {
            'fields': ('stock_quantity', 'is_in_stock', 'is_available')
        }),
        ('Габариты', {
            'fields': ('weight', 'color', 'length', 'width', 'height')
        }),
    )

@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)
    list_filter = ('parent',)

@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ('name', 'website')
    search_fields = ('name',)

@admin.register(Color)
class ColorAdmin(ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Collection)
class CollectionAdmin(ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    filter_horizontal = ('products',)

@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ('product', 'user', 'score', 'created_at')
    list_filter = ('score', 'created_at')
    search_fields = ('product__name', 'user__email')

class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'

    def clean_status(self):
        status = self.cleaned_data['status']
        order = self.instance
        if order.pk and (order.payment_id or order.payment_key):
            if order.status in ('pending', 'cancelled') and status != order.status:
                raise forms.ValidationError('Статус оплаты обновляется по данным ЮKassa.')
            if order.status in ('paid', 'processing', 'shipped', 'delivered') and status not in ('paid', 'processing', 'shipped', 'delivered'):
                raise forms.ValidationError('Оплаченный заказ нельзя повторно перевести в ожидание оплаты или отменить без отдельного возврата.')
        return status


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    form = OrderAdminForm
    list_display = ('id', 'user', 'status', 'stock_reserved', 'payment_review_required', 'total_amount', 'phone', 'city', 'created_at')
    list_filter = ('status', 'payment_review_required', 'stock_reserved', 'created_at')
    search_fields = ('user__email', 'id', 'email', 'phone', 'city')
    inlines = [OrderItemInline]
    readonly_fields = ('created_at', 'user', 'total_amount', 'payment_id', 'checkout_key',
        'payment_key', 'payment_started_at', 'payment_last_checked_at', 'confirmation_url',
        'stock_reserved', 'payment_review_required', 'delivery_method', 'delivery_cost', 'beyond_mkad')
    exclude = ('payment_request', 'checkout_fingerprint')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in ('pending', 'cancelled') and (obj.payment_id or obj.payment_key):
            return (*self.readonly_fields, 'status')
        return self.readonly_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Cart)
class CartAdmin(ModelAdmin):
    list_display = ('user', 'get_total_items', 'created_at')
    search_fields = ('user__email',)
    inlines = [CartItemInline]
    readonly_fields = ('created_at',)

    def get_total_items(self, obj):
        return sum(item.quantity for item in obj.items.all())
    get_total_items.short_description = "Всего товаров (шт.)"


@admin.register(Favorite)
class FavoriteAdmin(ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'product__name', 'product__sku')
    autocomplete_fields = ('user', 'product')
