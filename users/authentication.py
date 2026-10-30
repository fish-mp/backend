from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer, TokenVerifySerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import CustomUser


def access_for_refresh(refresh):
    access = refresh.access_token
    access['refresh_jti'] = refresh['jti']
    # Blacklist entries may be purged after refresh expiry: access must not
    # outlive the refresh token whose revocation it checks.
    access['exp'] = min(access['exp'], refresh['exp'])
    return str(access)


class VerifiedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        parent_jti = validated_token.get('refresh_jti')
        if (not user.is_email_verified or not parent_jti
                or BlacklistedToken.objects.filter(token__jti=parent_jti).exists()):
            raise AuthenticationFailed('Сессия завершена. Войдите снова.', code='session_revoked')
        return user


class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        if not user.is_email_verified:
            raise AuthenticationFailed('Подтвердите почту: перейдите по ссылке из письма.', code='email_not_verified')
        return super().get_token(user)

    def validate(self, attrs):
        email = attrs.get('email', '').strip()
        user = CustomUser.objects.filter(email__iexact=email).first()
        if user:
            attrs['email'] = user.email
        data = super().validate(attrs)
        if not self.user.is_email_verified:
            raise AuthenticationFailed('Подтвердите почту: перейдите по ссылке из письма.', code='email_not_verified')
        data['access'] = access_for_refresh(RefreshToken(data['refresh']))
        return data


class VerifiedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
        if not CustomUser.objects.filter(pk=refresh['user_id'], is_active=True, is_email_verified=True).exists():
            raise AuthenticationFailed('Войдите снова.', code='user_inactive')
        data = super().validate(attrs)
        data['access'] = access_for_refresh(RefreshToken(data.get('refresh', attrs['refresh'])))
        return data


class VerifiedTokenVerifySerializer(TokenVerifySerializer):
    def validate(self, attrs):
        authentication = VerifiedJWTAuthentication()
        authentication.get_user(authentication.get_validated_token(attrs['token']))
        return {}
