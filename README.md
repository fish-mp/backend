# fish backend
## Usage

### Create virtual environment

🔑 Copy `.env.example` to `.env` and change api settings

### Run project

🚀 Run project via `make up-build`


## Исправления авторизации и безопасности
Подтверждение email обязательно для API. Параметры SMTP и FRONTEND_URL приведены в .env.example.
DJANGO_SECRET_KEY обязателен: сгенерируйте случайный ключ, например через secrets.token_urlsafe(64).
Для разработки можно установить EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend.
После обновления зависимостей выполните python manage.py migrate.
Тесты: python manage.py test users shop courses.
Изменения API, результаты проверки и обязательные действия при внедрении описаны в [SECURITY_REVIEW.md](SECURITY_REVIEW.md).
