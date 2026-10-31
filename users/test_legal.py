import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from legal.catalog import catalog, REQUIRED
from users.models import CustomUser, LegalConsent
from shop.models import Cart, CartItem, Category, Product, Order
from shop.test_payments import provider
from courses.models import Course


class LegalConsentTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.operator = {'status':'published','name':'Test operator','legal_address':'Test address',
            'inn':'1234567890','contact_email':'privacy@example.com','data_location':'Russia',
            'consent_purposes':['registration','checkout','enrollment']}
        (self.root/'operator.json').write_text(json.dumps(self.operator), encoding='utf-8')
        for slug in REQUIRED:
            (self.root/(slug+'.json')).write_text(json.dumps({'slug':slug,'title':slug,
                'status':'published','version':'2026-10-31-v1',
                'sections':[{'title':'Test only','paragraphs':['Test text, not production legal text.']}]}), encoding='utf-8')
        self.override = override_settings(LEGAL_DOCUMENTS_ENABLED=True, LEGAL_DOCUMENTS_DIR=self.root,
            EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.registration = {'email':'new@example.com','password':'River-Planet-42!','first_name':'Anna','city':'Moscow','age':25}

    def consent(self):
        doc = next(d for d in catalog()['documents'] if d['slug']=='personal-data-consent')
        return {'accepted':True,'version':doc['version'],'sha256':doc['sha256']}

    def test_separate_consent_is_required_and_snapshot_is_saved(self):
        self.assertEqual(self.client.post('/api/users/register/',self.registration,format='json').status_code,400)
        self.assertFalse(CustomUser.objects.exists())
        response = self.client.post('/api/users/register/',{**self.registration,'privacy_consent':self.consent()},format='json')
        self.assertEqual(response.status_code,201)
        proof = LegalConsent.objects.get()
        self.assertEqual(proof.purpose,'registration')
        self.assertEqual(proof.document_sha256,self.consent()['sha256'])
        self.assertEqual(proof.document_snapshot['operator']['name'],'Test operator')
        self.assertIsNotNone(proof.accepted_at)

    def test_false_string_and_stale_hash_do_not_count_as_consent(self):
        for change in [{'accepted':False},{'accepted':'true'},{'version':'old'},{'sha256':'wrong'}]:
            response = self.client.post('/api/users/register/',{**self.registration,
                'privacy_consent':{**self.consent(),**change}},format='json')
            self.assertEqual(response.status_code,400)
        self.assertFalse(LegalConsent.objects.exists())

    def test_drafts_and_placeholder_operator_fail_closed_when_enabled(self):
        self.operator['name']='{{FILL_OPERATOR}}'
        (self.root/'operator.json').write_text(json.dumps(self.operator),encoding='utf-8')
        self.assertEqual(self.client.get('/api/legal/documents/').status_code,503)
        self.assertEqual(self.client.post('/api/users/register/',self.registration,format='json').status_code,503)
        self.assertFalse(CustomUser.objects.exists())

    @override_settings(LEGAL_DOCUMENTS_ENABLED=False)
    def test_inactive_preparation_does_not_publish_drafts_or_fake_existing_consents(self):
        config=self.client.get('/api/legal/documents/').data
        self.assertFalse(config['ready'])
        self.assertEqual(config['documents'],[])
        self.assertEqual(self.client.post('/api/users/register/',self.registration,format='json').status_code,201)
        self.assertFalse(LegalConsent.objects.exists())

    def test_new_text_invalidates_old_hash_and_keeps_old_snapshot(self):
        payload=self.consent()
        self.client.post('/api/users/register/',{**self.registration,'privacy_consent':payload},format='json')
        source=self.root/'personal-data-consent.json'
        changed=json.loads(source.read_text())
        changed['sections'][0]['paragraphs']=['Updated test text.']
        source.write_text(json.dumps(changed),encoding='utf-8')
        self.assertNotEqual(payload['sha256'],self.consent()['sha256'])
        self.assertEqual(LegalConsent.objects.get().document_sha256,payload['sha256'])
        self.assertIn('Test text',LegalConsent.objects.get().document_snapshot['sections'][0]['paragraphs'][0])

    @patch('shop.payments.Payment.create',side_effect=provider)
    def test_offer_acceptance_cannot_replace_personal_data_consent(self,create):
        user=CustomUser.objects.create_user('buyer@example.com','River-Planet-42!',is_email_verified=True)
        self.client.force_authenticate(user)
        category=Category.objects.create(name='Plants')
        product=Product.objects.create(name='Plant',sku='plant',price=100,stock_quantity=1,category=category)
        cart=Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart,product=product)
        checkout={'email':user.email,'phone':'+79991234567','offer_accepted':True}
        self.assertEqual(self.client.post('/api/orders/',checkout,format='json').status_code,400)
        create.assert_not_called()
        self.assertFalse(Order.objects.exists())
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity,1)
        result=self.client.post('/api/orders/',{**checkout,'privacy_consent':self.consent()},format='json')
        self.assertEqual(result.status_code,201)
        self.assertEqual(LegalConsent.objects.get().purpose,'checkout')

    def test_course_application_records_separate_consent(self):
        user=CustomUser.objects.create_user('student@example.com','River-Planet-42!',is_email_verified=True)
        self.client.force_authenticate(user)
        course=Course.objects.create(title='Test course',is_free=True)
        url='/api/courses/'+str(course.pk)+'/enroll/'
        self.assertEqual(self.client.post(url,{},format='json').status_code,400)
        self.assertEqual(self.client.post(url,{'privacy_consent':self.consent()},format='json').status_code,200)
        self.assertEqual(LegalConsent.objects.get().purpose,'enrollment')
