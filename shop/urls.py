from django.urls import path, include
from rest_framework.routers import DefaultRouter
from shop.views import BrandViewSet, CategoryViewSet, ProductViewSet, CollectionViewSet, ReviewViewSet, FavoriteViewSet, CartViewSet, CartItemViewSet, OrderViewSet

router = DefaultRouter()
router.register(r'brands', BrandViewSet, basename='brands')
router.register(r'categories', CategoryViewSet, basename='categories')
router.register(r'products', ProductViewSet, basename='products')
router.register(r'collections', CollectionViewSet, basename='collections')

router.register(r'reviews', ReviewViewSet, basename='reviews')

router.register(r'favorites', FavoriteViewSet, basename='favorites')

router.register(r'cart', CartViewSet, basename='cart')
router.register(r'cart-items', CartItemViewSet, basename='cart-item')

router.register(r'orders', OrderViewSet, basename='orders')

urlpatterns = [
    path('', include(router.urls)),
]