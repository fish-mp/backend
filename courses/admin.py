from unfold.admin import ModelAdmin, TabularInline
from django.contrib import admin

# Register your models here.

from courses.models import Course, Files, Enrollment
@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ('title', 'description', 'short_description')
    search_fields = ('title', 'description')
@admin.register(Files)
class FilesAdmin(ModelAdmin):
    list_display = ('title', 'file')
    search_fields = ('title',)

@admin.register(Enrollment)
class EnrollmentAdmin(ModelAdmin):
    list_display = ('user', 'course', 'state')
    search_fields = ('user__email', 'course__title', 'state')
    list_filter = ('state',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'