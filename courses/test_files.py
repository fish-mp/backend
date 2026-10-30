import tempfile
from urllib.parse import urlsplit
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from courses.models import Course, Enrollment, Files
from users.models import CustomUser


class ProtectedCourseFilesTests(APITestCase):
    def setUp(self):
        cache.clear()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        override = override_settings(MEDIA_ROOT=temporary.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = CustomUser.objects.create_user('student@example.com', 'River-Planet-42!', is_email_verified=True)
        self.material = Files.objects.create(title='Lecture', file=SimpleUploadedFile('lecture.mp4', b'course-content'))
        self.course = Course.objects.create(title='Course', description='Description')
        self.course.files.add(self.material)
        self.enrollment = Enrollment.objects.create(course=self.course, user=self.user, state='enrolled')
        self.tokens = self.client.post('/api/token/', {'email': self.user.email, 'password': 'River-Planet-42!'}).data
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.tokens['access'])
        data = self.client.get(f'/api/courses/{self.course.pk}/').data
        self.url = data['files'][0]['file']
        self.client.credentials()

    def test_known_media_path_requires_authorization(self):
        self.assertEqual(self.client.get('/media/' + self.material.file.name).status_code, 403)
        self.assertEqual(self.client.get(urlsplit(self.url).path).status_code, 403)

    def test_signed_link_serves_material_and_does_not_cache(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'course-content')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        response.close()

    def test_logout_revokes_existing_download_link(self):
        self.client.post('/api/users/logout/', {'refresh': self.tokens['refresh']})
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_expiry_and_revoked_enrollment_deny_download(self):
        with override_settings(COURSE_FILE_URL_MAX_AGE=-1):
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.enrollment.state = 'applied'
        self.enrollment.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_teacher_material_does_not_belong_to_student(self):
        self.material.for_teacher = True
        self.material.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_nginx_internal_redirect_and_staff_admin_link(self):
        with override_settings(COURSE_FILES_USE_X_ACCEL_REDIRECT=True):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['X-Accel-Redirect'].startswith('/_protected_courses/'))
        staff = CustomUser.objects.create_superuser('admin@example.com', 'River-Planet-42!')
        self.client.force_login(staff)
        response = self.client.get('/media/' + self.material.file.name)
        self.assertEqual(response.status_code, 200)
        response.close()
