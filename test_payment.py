import os
import traceback
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "service.settings")
django.setup()

from django.conf import settings
from django.core.mail import send_mail
import requests
from shop.models import Order
from shop.views import build_order_summary


def run_diagnostics():
    print("=== 1. Проверка настроек из .env ===")
    print(f"TELEGRAM_BOT_TOKEN: {'Задан' if settings.TELEGRAM_BOT_TOKEN else 'НЕ ЗАДАН'}")
    print(f"TELEGRAM_CHAT_ID: {settings.TELEGRAM_CHAT_ID or 'НЕ ЗАДАН'}")
    print(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'НЕ ЗАДАН')}:{getattr(settings, 'EMAIL_PORT', '')}")
    print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER or 'НЕ ЗАДАН'}")
    print(f"SELLER_NOTIFICATION_EMAILS: {getattr(settings, 'SELLER_NOTIFICATION_EMAILS', [])}")
    print("====================================\n")

    # Берем последний созданный заказ (независимо от статуса, чтобы не оформлять заново)
    order = Order.objects.order_by("-created_at").first()
    if not order:
        print("В базе нет ни одного заказа! Оформите заказ на сайте.")
        return

    print(f"Используем заказ №{order.id} (Сумма: {order.total_amount} ₽, Покупатель: {order.email})")
    summary_text = build_order_summary(order)
    print("\n--- Сформированный текст уведомления ---")
    print(summary_text)
    print("----------------------------------------\n")

    # ШАГ 1: Тестируем Telegram напрямую
    print(">>> Шаг 1: Отправка в Telegram...")
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": summary_text},
            timeout=15,
        )
        print(f"Статус ответа Telegram: {resp.status_code}")
        print(f"Ответ Telegram: {resp.text}\n")
    except Exception:
        print("❌ ОШИБКА при отправке в Telegram:")
        traceback.print_exc()
        print()

    # ШАГ 2: Тестируем письмо менеджеру
    print(">>> Шаг 2: Отправка письма менеджеру...")
    try:
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        recipients = getattr(settings, "SELLER_NOTIFICATION_EMAILS", [])
        sent = send_mail(
            subject=f"Оплачен новый заказ №{order.id} на сумму {order.total_amount} ₽",
            message=summary_text,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=False,
        )
        print(f"✅ Успешно! Отправлено писем менеджеру ({recipients}): {sent}\n")
    except Exception:
        print("❌ ОШИБКА при отправке письма менеджеру:")
        traceback.print_exc()
        print()

    # ШАГ 3: Тестируем письмо покупателю
    print(">>> Шаг 3: Отправка письма покупателю...")
    try:
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        message = (
            f"Здравствуйте!\n\n"
            f"Ваш заказ №{order.id} сформирован, нужно дождаться, когда менеджер с вами свяжется.\n\n"
            f"Спасибо за покупку в FishKids!"
        )
        sent = send_mail(
            subject=f"Заказ №{order.id} сформирован — FishKids",
            message=message,
            from_email=from_email,
            recipient_list=[order.email],
            fail_silently=False,
        )
        print(f"✅ Успешно! Отправлено писем покупателю ({order.email}): {sent}\n")
    except Exception:
        print("❌ ОШИБКА при отправке письма покупателю:")
        traceback.print_exc()
        print()


if __name__ == "__main__":
    run_diagnostics()