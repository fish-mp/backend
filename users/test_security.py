import re
from unittest.mock import patch
from urllib.parse import unquote

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from users.models import CustomUser


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.payload = {'email': 'new@example.com', 'password': 'River-Planet-42!',
                        'first_name': 'Анна', 'city': 'Москва', 'age': 25}

    def token(self):
        return unquote(re.search(r'#token=([^\s]+)', mail.outbox[-1].body).group(1))

    def login(self):
        return self.client.post('/api/token/', {'email': self.payload['email'], 'password': self.payload['password']})

    def test_registration_requires_one_time_email_confirmation(self):
        self.assertEqual(self.client.post('/api/users/register/', self.payload).status_code, 201)
        self.assertFalse(CustomUser.objects.get().is_email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertEqual(self.login().status_code, 401)
        token = self.token()
        self.assertEqual(self.client.post('/api/users/verify-email/', {'token': token}).status_code, 200)
        self.assertEqual(self.client.post('/api/users/verify-email/', {'token': token}).status_code, 400)
        self.assertEqual(self.login().status_code, 200)

    def test_invalid_expired_and_changed_email_links_fail(self):
        self.client.post('/api/users/register/', self.payload)
        token = self.token()
        self.assertEqual(self.client.post('/api/users/verify-email/', {'token': token + 'x'}).status_code, 400)
        with override_settings(EMAIL_VERIFICATION_TIMEOUT=-1):
            self.assertEqual(self.client.post('/api/users/verify-email/', {'token': token}).status_code, 400)
        CustomUser.objects.update(email='changed@example.com')
        self.assertEqual(self.client.post('/api/users/verify-email/', {'token': token}).status_code, 400)

    def test_weak_password_and_case_variant_are_rejected(self):
        self.assertEqual(self.client.post('/api/users/register/', {**self.payload, 'password': '123'}).status_code, 400)
        self.client.post('/api/users/register/', self.payload)
        self.assertEqual(self.client.post('/api/users/register/', {**self.payload, 'email': 'NEW@example.com'}).status_code, 400)

    def test_mail_failure_does_not_leave_a_registered_account(self):
        with patch('users.views.send_verification_email', side_effect=OSError('SMTP unavailable')):
            self.assertEqual(self.client.post('/api/users/register/', self.payload).status_code, 503)
        self.assertFalse(CustomUser.objects.exists())

    def test_email_template_escapes_user_content(self):
        payload = {**self.payload, 'first_name': '<img src=x onerror=alert(1)>'}
        self.assertEqual(self.client.post('/api/users/register/', payload).status_code, 201)
        html = mail.outbox[-1].alternatives[0][0]
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img', html)

    def test_resend_is_generic_and_does_not_authenticate(self):
        self.client.post('/api/users/register/', self.payload)
        pending = self.client.post('/api/users/resend-verification/', {'email': self.payload['email']})
        missing = self.client.post('/api/users/resend-verification/', {'email': 'missing@example.com'})
        self.assertEqual(pending.data, missing.data)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.login().status_code, 401)

    def test_logout_revokes_access_and_refresh_after_rotation(self):
        CustomUser.objects.create_user(self.payload['email'], self.payload['password'], is_email_verified=True)
        tokens = self.login().data
        access = AccessToken(tokens['access'])
        self.assertLessEqual(access['exp'] - access['iat'], 300)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        rotated = self.client.post('/api/token/refresh/', {'refresh': tokens['refresh']}).data
        self.assertNotEqual(tokens['refresh'], rotated['refresh'])
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + rotated['access'])
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.assertEqual(self.client.post('/api/users/logout/', {'refresh': rotated['refresh']}).status_code, 204)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        self.assertEqual(self.client.post('/api/token/refresh/', {'refresh': rotated['refresh']}).status_code, 401)
        self.assertEqual(self.client.post('/api/users/logout/', {'refresh': rotated['refresh']}).status_code, 204)

    def test_unverified_refresh_and_legacy_access_are_rejected(self):
        user = CustomUser.objects.create_user(self.payload['email'], self.payload['password'])
        refresh = RefreshToken.for_user(user)
        self.assertEqual(self.client.post('/api/token/refresh/', {'refresh': str(refresh)}).status_code, 401)
        user.is_email_verified = True
        user.save()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(refresh.access_token))
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)

    def test_admin_cookie_cannot_authenticate_customer_api(self):
        user = CustomUser.objects.create_superuser('admin@example.com', 'Admin-Planet-42!')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/cart/').status_code, 401)

    def test_auth_is_rate_limited(self):
        for _ in range(30):
            self.client.post('/api/token/', {'email': 'x@example.com', 'password': 'wrong'})
        self.assertEqual(self.client.post('/api/token/', {'email': 'x@example.com', 'password': 'wrong'}).status_code, 429)

    def test_auth_fields_reject_non_object_json(self):
        for url in ['/api/users/verify-email/', '/api/users/resend-verification/', '/api/users/logout/']:
            self.assertEqual(self.client.post(url, [], format='json').status_code, 400)
