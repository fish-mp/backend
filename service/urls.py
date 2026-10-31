"""
URL configuration for service project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from django.conf import settings
from django.conf.urls.static import static
from shop.views import YooKassaWebhookView
from courses.views import SchoolViewSet, TeacherViewSet, LandingPageAPIView
from courses.file_access import CourseFileView
from users.views import LoginView, RefreshView, VerifyView

schema_view = get_schema_view(
   openapi.Info(title="Snippets API", default_version='v1', public=True),
   url="http://127.0.0.1:8000/",
   permission_classes=(permissions.AllowAny,),
)

school_router = SimpleRouter()
school_router.register(r'schools', SchoolViewSet, basename='schools')
school_router.register(r'teachers', TeacherViewSet, basename='teachers')

from legal.views import LegalDocumentsView

urlpatterns = [
    path('api/legal/documents/', LegalDocumentsView.as_view(), name='legal-documents'),
    path('admin/', admin.site.urls),
    path('api/course-files/<int:pk>/<str:name>', CourseFileView.as_view(), name='course-file-download'),
    path('media/files/<path:filename>', CourseFileView.as_view(), name='legacy-course-file'),
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', RefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', VerifyView.as_view(), name='token_verify'),
    path('api/landing/', LandingPageAPIView.as_view(), name='landing-page'),
    path('api/', include(school_router.urls)),
    path('api/users/', include('users.urls')),
    path('api/events/', include('events.urls')),
    path('api/news/', include('news.urls')),
    path('api/courses/', include('courses.urls')),
    path('api/', include('shop.urls')),
    path('api/yookassa-webhook/', YooKassaWebhookView.as_view(), name='yookassa_webhook'),
    path('api/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
