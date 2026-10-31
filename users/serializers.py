from rest_framework import serializers
from users.models import CustomUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from legal.catalog import validate_consent, record_consent

class UserRegistrationSerializer(serializers.ModelSerializer):
    privacy_consent = serializers.JSONField(required=False, write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    
    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'first_name', 'city', 'age', 'privacy_consent')
        extra_kwargs = {
            'password': {'write_only': True},
            'first_name': {'required': True, 'allow_blank': False},
            'city': {'required': True, 'allow_blank': False},
            'age': {'required': True},
        }
    
    def validate_first_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Поле 'Имя' не может быть пустым")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Этот email уже зарегистрирован. Войдите или запросите письмо подтверждения.")
        return value

    def validate(self, attrs):
        validate_consent(attrs.get('privacy_consent'), 'registration')
        try:
            validate_password(attrs['password'], CustomUser(**{k:v for k,v in attrs.items() if k != 'privacy_consent'}))
        except ValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return attrs

    def validate_city(self, value):
        if not value.strip():
            raise serializers.ValidationError("Поле 'Город' не может быть пустым")
        return value

    def validate_age(self, value):
        if value is None:
            raise serializers.ValidationError("Поле 'Возраст' обязательно для заполнения")
        if value < 0:
            raise serializers.ValidationError("Возраст не может быть отрицательным")
        return value
    
    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            city=validated_data.get('city', ''),
            age=validated_data.get('age')
        )
        record_consent(user, 'registration', validated_data.get('privacy_consent'), user.pk)
        return user
