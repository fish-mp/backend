from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


EMAIL_VERIFICATION_SALT = 'users.verify-email.v1'


def send_verification_email(user):
    token = signing.dumps({'user_id': user.pk, 'email': user.email}, salt=EMAIL_VERIFICATION_SALT)
    context = {
        'first_name': user.first_name,
        'verification_url': f'{settings.FRONTEND_URL}/verify-email#token={quote(token)}',
        'email': user.email,
        'expires_hours': settings.EMAIL_VERIFICATION_TIMEOUT // 3600,
    }
    message = EmailMultiAlternatives(
        subject='Подтвердите почту — FishKids',
        body=render_to_string('users/verify_email.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(render_to_string('users/verify_email.html', context), 'text/html')
    message.send(fail_silently=False)
