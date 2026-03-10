from django.db import models
from django.utils import timezone

class News(models.Model):
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    text = models.TextField(verbose_name="Текст новости")
    
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    updated_at = models.DateTimeField(default=timezone.now, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class NewsPhoto(models.Model):
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name='photos', verbose_name="Новость")
    image = models.ImageField(upload_to='news/photos/', verbose_name="Фотография")
    description = models.CharField(max_length=255, blank=True, verbose_name="Описание")
    
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Фотография к новости"
        verbose_name_plural = "Фотографии к новостям"