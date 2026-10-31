from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_email_verified', True)
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True, verbose_name="Email")
    is_email_verified = models.BooleanField(default=False, verbose_name="Почта подтверждена")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Имя")
    city = models.CharField(max_length=100, blank=True, verbose_name="Город")
    age = models.PositiveIntegerField(null=True, blank=True, verbose_name="Возраст")

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        constraints = [models.UniqueConstraint(Lower('email'), name='users_email_ci_unique')]



class LegalConsent(models.Model):
    user = models.ForeignKey('CustomUser', null=True, on_delete=models.SET_NULL, related_name='legal_consents')
    purpose = models.CharField(max_length=30, choices=[
        ('registration', 'Регистрация'), ('checkout', 'Оформление заказа'), ('enrollment', 'Запись на курс')])
    object_id = models.CharField(max_length=64, blank=True)
    document_version = models.CharField(max_length=64)
    document_sha256 = models.CharField(max_length=64)
    document_snapshot = models.JSONField()
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Подтверждение согласия'
        verbose_name_plural = 'Подтверждения согласий'
