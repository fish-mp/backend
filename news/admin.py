from django.utils.html import format_html
from .models import News, NewsPhoto
from unfold.admin import ModelAdmin, TabularInline
from django.contrib import admin

class NewsPhotoInline(TabularInline):
    model = NewsPhoto
    extra = 1
    readonly_fields = ['photo_preview']
    fields = ('image', 'description', 'created_at', 'photo_preview')
    
    def photo_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px;"/>', obj.image.url)
        return "Нет изображения"
    photo_preview.short_description = "Предпросмотр"


@admin.register(News)
class NewsAdmin(ModelAdmin):
    list_display = ('title', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'text')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'text')
        }),
        ('Настройки публикации', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    inlines = [NewsPhotoInline]


@admin.register(NewsPhoto)
class NewsPhotoAdmin(ModelAdmin):
    list_display = ('news', 'description', 'photo_preview', 'created_at')
    list_filter = ('news', 'created_at')
    search_fields = ('news__title', 'description')
    
    def photo_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px;"/>', obj.image.url)
        return "Нет изображения"
    photo_preview.short_description = "Фото"