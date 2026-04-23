from django.contrib import admin
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

@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__email', 'id')
    inlines = [OrderItemInline]
    readonly_fields = ('created_at',)

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
