from pathlib import Path
from urllib.parse import quote
import mimetypes

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import content_disposition_header
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from courses.models import Enrollment, Files
from users.authentication import VerifiedJWTAuthentication

SALT = 'courses.file-access.v1'


def file_url(file, request):
    if not request or not request.user.is_authenticated or not request.auth:
        return None
    ticket = signing.dumps({'file': file.pk, 'user': request.user.pk,
                            'refresh_jti': request.auth['refresh_jti']}, salt=SALT)
    url = reverse('course-file-download', kwargs={'pk': file.pk, 'name': Path(file.file.name).name})
    return request.build_absolute_uri(url) + '?ticket=' + quote(ticket)


class CourseFileView(APIView):
    # Admin file links may use the admin session. Customer API authentication
    # remains JWT-only; native video/download requests use a signed ticket.
    authentication_classes = [VerifiedJWTAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, pk=None, name=None, filename=None):
        material = get_object_or_404(Files, pk=pk) if pk is not None else get_object_or_404(Files, file='files/' + filename)
        user = request.user
        if not (user.is_authenticated and (user.is_staff or request.auth)):
            try:
                ticket = signing.loads(request.query_params.get('ticket', ''), salt=SALT,
                                       max_age=settings.COURSE_FILE_URL_MAX_AGE)
                if ticket['file'] != material.pk or not ticket.get('refresh_jti'):
                    raise PermissionDenied()
                if BlacklistedToken.objects.filter(token__jti=ticket['refresh_jti']).exists():
                    raise PermissionDenied()
                user = get_user_model().objects.get(pk=ticket['user'], is_active=True, is_email_verified=True)
            except (signing.BadSignature, KeyError, TypeError, get_user_model().DoesNotExist):
                raise PermissionDenied('Нет доступа к материалу.')
        if not user.is_active or not user.is_email_verified:
            raise PermissionDenied('Нет доступа к материалу.')
        if not user.is_staff and (material.for_teacher or not Enrollment.objects.filter(
                user=user, course__files=material, state='enrolled').exists()):
            raise PermissionDenied('Нет доступа к материалу.')
        root = (Path(settings.MEDIA_ROOT) / 'files').resolve()
        path = Path(material.file.path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise Http404()
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        attachment = not content_type.startswith(('video/', 'audio/'))
        if settings.COURSE_FILES_USE_X_ACCEL_REDIRECT:
            response = HttpResponse(content_type=content_type)
            response['X-Accel-Redirect'] = '/_protected_courses/' + quote(path.relative_to(root).as_posix())
            response['Content-Disposition'] = content_disposition_header(attachment, path.name)
        else:
            response = FileResponse(path.open('rb'), as_attachment=attachment, filename=path.name, content_type=content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
