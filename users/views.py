import logging
from smtplib import SMTPException

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from users.authentication import (VerifiedTokenObtainPairSerializer, VerifiedTokenRefreshSerializer,
                                  VerifiedTokenVerifySerializer)
from users.emails import EMAIL_VERIFICATION_SALT, send_verification_email
from users.models import CustomUser
from users.serializers import UserRegistrationSerializer
from users.throttles import AuthRateThrottle, EmailRateThrottle

logger = logging.getLogger(__name__)


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [EmailRateThrottle]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
                send_verification_email(user)
        except IntegrityError:
            return Response({'email': ['Этот email уже зарегистрирован.']}, status=400)
        except (SMTPException, OSError):
            logger.exception('Не удалось отправить письмо подтверждения')
            return Response({'detail': 'Не удалось отправить письмо. Попробуйте позже.'}, status=503)
        return Response({'message': 'Проверьте почту — мы отправили ссылку для подтверждения.'}, status=201)


class EmailVerificationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        token = serializers.CharField(max_length=1024).run_validation(serializers.DictField().run_validation(request.data).get('token'))
        try:
            data = signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
        except signing.BadSignature:
            return Response({'detail': 'Ссылка недействительна или устарела. Запросите новое письмо.'}, status=400)
        updated = CustomUser.objects.filter(pk=data['user_id'], email=data['email'],
                                            is_active=True, is_email_verified=False).update(is_email_verified=True)
        if not updated:
            return Response({'detail': 'Ссылка уже использована или недействительна.'}, status=400)
        return Response({'message': 'Почта подтверждена. Теперь можно войти.'})


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [EmailRateThrottle]

    def post(self, request):
        email = serializers.EmailField().run_validation(serializers.DictField().run_validation(request.data).get('email')).strip()
        user = CustomUser.objects.filter(email__iexact=email, is_active=True, is_email_verified=False).first()
        if user:
            try:
                send_verification_email(user)
            except (SMTPException, OSError):
                logger.exception('Не удалось повторно отправить письмо подтверждения')
        return Response({'message': 'Если адрес ожидает подтверждения, письмо отправлено.'}, status=202)


class LogoutView(APIView):
    # The refresh token is the logout credential; access may already be expired.
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        token = serializers.CharField(max_length=2048).run_validation(serializers.DictField().run_validation(request.data).get('refresh'))
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserRegistrationSerializer(request.user).data)


class LoginView(TokenObtainPairView):
    serializer_class = VerifiedTokenObtainPairSerializer
    throttle_classes = [AuthRateThrottle]


class RefreshView(TokenRefreshView):
    serializer_class = VerifiedTokenRefreshSerializer
    throttle_classes = [AuthRateThrottle]


class VerifyView(TokenVerifyView):
    serializer_class = VerifiedTokenVerifySerializer
    throttle_classes = [AuthRateThrottle]
