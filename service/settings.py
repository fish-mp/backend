import os
from datetime import timedelta
from decouple import config  # type: ignore
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY: str = config(
    "DJANGO_SECRET_KEY", cast=str
)
if len(SECRET_KEY) < 50 or SECRET_KEY == 'django-default-secret-key':
    raise ImproperlyConfigured('Set a random DJANGO_SECRET_KEY of at least 50 characters.')

DEBUG: bool = config("DEBUG", default=False, cast=bool)

LANGUAGE_CODE = 'ru-ru'

YOOKASSA_SHOP_ID = config("YOOKASSA_SHOP_ID", default="", cast=str)
YOOKASSA_SECRET_KEY = config("YOOKASSA_SECRET_KEY", default="", cast=str)
# Ставка НДС для чека (54-ФЗ): 1 — без НДS, 2 — 0%, 3 — 10%, 4 — 20%, 5 — 10/110, 6 — 20/120
YOOKASSA_VAT_CODE = config("YOOKASSA_VAT_CODE", default=1, cast=int)

# Telegram-уведомления продавцу об оплаченных заказах.
# TELEGRAM_BOT_TOKEN — токен бота от @BotFather; TELEGRAM_CHAT_ID — id чата/группы продавца.
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="", cast=str)
TELEGRAM_CHAT_ID = config("TELEGRAM_CHAT_ID", default="", cast=str)

INSTALLED_APPS = [
    # Admin UI
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    # "unfold.contrib.import_export", optional, if django-import-export package is used
    # "unfold.contrib.guardian",  optional, if django-guardian package is used
    # "unfold.contrib.simple_history",   optional, if django-simple-history package is used

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.postgres",
    # Apps
    "users.apps.UsersConfig",
    'events.apps.EventsConfig',
    'news.apps.NewsConfig',
    'courses.apps.CoursesConfig',
    "shop.apps.ShopConfig",
    # Plugins
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    'drf_yasg',
    'django_filters',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "users.authentication.VerifiedJWTAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"auth": "30/min", "email": "5/hour"},
    "NUM_PROXIES": 1,
}

ROOT_URLCONF = "service.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates'],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "service.wsgi.application"

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": config("DB_NAME", default="postgres", cast=str),
#         "USER": config("DB_USER", default="postgres", cast=str),
#         "PASSWORD": config("DB_PASS", default="postgres", cast=str),
#         "HOST": config("DB_HOST", default="localhost", cast=str),
#         "PORT": config("DB_PORT", default="5432", cast=str),
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'data.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": "",
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.\
default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}

ASGI_APPLICATION = "service.asgi.application"

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "https://fishkids.ru",
    "https://www.fishkids.ru",
    "https://inco-edu.ru",
    "https://www.inco-edu.ru",

]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:5173",
    "https://fishkids.ru",
    "https://www.fishkids.ru",
    "https://inco-edu.ru",
    "https://www.inco-edu.ru",
    "https://fish-mp.miv-dev.ru",
    "https://fish-mp.netlify.app",
]

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "fish-mp.miv-dev.ru",
    "fish-mp.netlify.app",
    "fishkids.ru",
    "www.fishkids.ru",
    "inco-edu.ru",
    "www.inco-edu.ru",
]

CORS_ALLOW_CREDENTIALS = False

# Разрешаем любые источники только в режиме разработки.
# В проде работает строгий белый список CORS_ALLOWED_ORIGINS выше.
CORS_ALLOW_ALL_ORIGINS = DEBUG
AUTH_USER_MODEL = 'users.CustomUser'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

FRONTEND_URL = config('FRONTEND_URL', default='https://fishkids.ru').rstrip('/')
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='FishKids <noreply@fishkids.ru>')
DEFAULT_REPLY_TO_EMAIL = config('DEFAULT_REPLY_TO_EMAIL', default='')
EMAIL_VERIFICATION_TIMEOUT = 24 * 60 * 60
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

COURSE_FILE_URL_MAX_AGE = 3600
COURSE_FILES_USE_X_ACCEL_REDIRECT = config('COURSE_FILES_USE_X_ACCEL_REDIRECT', default=False, cast=bool)
