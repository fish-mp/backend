"""Versioned legal text; drafts cannot be accepted as consent."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import APIException, ValidationError

REQUIRED = ('privacy-policy', 'personal-data-consent', 'cookies-policy', 'public-offer', 'returns-policy')


def catalog(preview=False):
    enabled = settings.LEGAL_DOCUMENTS_ENABLED
    if not enabled and not preview:
        return {'ready': False, 'documents': [], 'consent_purposes': [], 'contact_email': ''}
    root = Path(settings.LEGAL_DOCUMENTS_DIR)
    try:
        operator = json.loads((root / 'operator.json').read_text(encoding='utf-8'))
        documents = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(root.glob('*.json')) if p.name != 'operator.json']
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured('Legal documents cannot be loaded') from exc
    if enabled:
        required_operator = ['name', 'legal_address', 'contact_email', 'data_location']
        if operator.get('status') != 'published' or any(not operator.get(k) for k in required_operator):
            raise ImproperlyConfigured('Fill and publish legal operator details')
        if '{{' in json.dumps(operator, ensure_ascii=False):
            raise ImproperlyConfigured('Legal operator details still contain placeholders')
        by_slug = {d.get('slug'): d for d in documents}
        for slug in REQUIRED:
            doc = by_slug.get(slug)
            if not doc or doc.get('status') != 'published' or not doc.get('version') or not doc.get('sections'):
                raise ImproperlyConfigured('Publish legal document: ' + slug)
            if '{{' in json.dumps(doc, ensure_ascii=False) or str(doc['version']).startswith('draft'):
                raise ImproperlyConfigured('Legal document contains placeholders: ' + slug)
        documents = [d for d in documents if d.get('status') == 'published']
        for doc in documents:
            if (not doc.get('title') or not doc.get('version') or '{{' in json.dumps(doc, ensure_ascii=False)
                    or not isinstance(doc.get('sections'), list)
                    or any(not isinstance(s, dict) or not s.get('title') or not isinstance(s.get('paragraphs'), list)
                           or not s['paragraphs'] or any(not isinstance(p, str) or not p.strip() for p in s['paragraphs'])
                           for s in doc['sections'])):
                raise ImproperlyConfigured('Invalid legal document content')
        if any(p not in ('registration','checkout','enrollment') for p in operator.get('consent_purposes', [])):
            raise ImproperlyConfigured('Unknown legal consent purpose')
    result = []
    public_operator = {k: operator.get(k, '') for k in ['name', 'legal_address', 'inn', 'ogrn', 'contact_email', 'data_location']}
    for doc in documents:
        snapshot = {**doc, 'operator': public_operator}
        digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        result.append({**snapshot, 'sha256': digest})
    return {'ready': enabled, 'documents': result,
            'consent_purposes': operator.get('consent_purposes', []),
            'contact_email': operator.get('contact_email', '') if enabled else ''}


def validate_consent(payload, purpose):
    try:
        config = catalog()
    except ImproperlyConfigured:
        error = APIException('Документы временно недоступны. Попробуйте позже.')
        error.status_code = 503
        raise error
    if not config['ready']:
        if payload is not None:
            raise ValidationError({'privacy_consent': 'Согласие нельзя принять до публикации документа.'})
        return None
    if purpose not in config['consent_purposes']:
        return None
    doc = next(d for d in config['documents'] if d['slug'] == 'personal-data-consent')
    if (not isinstance(payload, dict) or payload.get('accepted') is not True
            or payload.get('version') != doc['version'] or payload.get('sha256') != doc['sha256']):
        raise ValidationError({'privacy_consent': 'Подтвердите отдельное согласие на обработку персональных данных. Если текст обновился, обновите страницу и прочитайте его заново.'})
    return doc


def record_consent(user, purpose, payload, object_id=''):
    document = validate_consent(payload, purpose)
    if document:
        from users.models import LegalConsent
        return LegalConsent.objects.create(user=user, purpose=purpose,
            object_id=str(object_id), document_version=document['version'],
            document_sha256=document['sha256'], document_snapshot={k:v for k,v in document.items() if k != 'sha256'})
