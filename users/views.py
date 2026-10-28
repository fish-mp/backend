import logging
import threading
from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from users.serializers import UserRegistrationSerializer

logger = logging.getLogger(__name__)


def send_registration_seller_email(user_data: dict):
    """Отправляет уведомление владельцу сайта о регистрации нового пользователя."""
    recipient_list = getattr(settings, "SELLER_NOTIFICATION_EMAILS", [])
    from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
    if not recipient_list or not from_email:
        return

    message = (
        f"👤 На сайте зарегистрировался новый пользователь!\n\n"
        f"ID: {user_data['id']}\n"
        f"Имя: {user_data['first_name']}\n"
        f"Email: {user_data['email']}\n"
        f"Город: {user_data['city']}\n"
        f"Возраст: {user_data['age']}"
    )

    try:
        send_mail(
            subject=f"Новая регистрация на сайте — {user_data['email']}",
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Не удалось отправить email владельцу о регистрации пользователя %s",
            user_data["email"],
        )


def notify_seller_user_registered(user):
    """Собирает данные пользователя и запускает отправку письма в фоновом потоке."""
    user_data = {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "city": user.city,
        "age": user.age,
    }
    threading.Thread(
        target=send_registration_seller_email,
        args=(user_data,),
        daemon=True,
    ).start()


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            notify_seller_user_registered(user)
            return Response(
                {
                    "message": "Пользователь успешно зарегистрирован",
                    "user": UserRegistrationSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)