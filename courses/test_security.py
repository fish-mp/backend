from rest_framework.test import APITestCase
from courses.models import Course
from users.models import CustomUser


class CoursePermissionTests(APITestCase):
    def test_course_api_is_read_only_for_all_api_clients(self):
        course = Course.objects.create(title='Курс', description='Описание')
        for user in [None, CustomUser.objects.create_superuser('admin@example.com', 'Admin-Planet-42!')]:
            self.client.force_authenticate(user)
            for method in ['patch', 'put', 'delete']:
                self.assertEqual(getattr(self.client, method)(f'/api/courses/{course.pk}/', {'title': 'changed'}).status_code, 405)
        course.refresh_from_db()
        self.assertEqual(course.title, 'Курс')

    def test_paid_course_application_does_not_grant_materials(self):
        from courses.models import Enrollment, CourseModule, Files
        course = Course.objects.create(title='Paid', description='Course', is_free=False)
        CourseModule.objects.create(course=course, title='Lecture', content='private lecture')
        file = Files.objects.create(title='Material', file='files/private.pdf')
        course.files.add(file)
        user = CustomUser.objects.create_user('student@example.com', 'River-Planet-42!', is_email_verified=True)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post(f'/api/courses/{course.pk}/enroll/').status_code, 200)
        self.assertEqual(Enrollment.objects.get(user=user, course=course).state, 'applied')
        response = self.client.get(f'/api/courses/{course.pk}/')
        self.assertEqual(response.data['files'], [])
        self.assertEqual(response.data['modules'][0]['content'], '')
