from unfold.admin import ModelAdmin, StackedInline
from django.contrib import admin
from courses.models import *

# Register your models here.
class CourseInline(StackedInline):
    model = Course
    extra = 0  # Не показывать пустые формы для новых курсов
    fields = ['title', 'short_description']
    show_change_link = True  # Показывать ссылку на редактирование курса

@admin.register(Tag)
class TagAdmin(ModelAdmin):
    list_display = ('name', 'course_count')
    search_fields = ('name',)
    inlines = [CourseInline]  # Показывать курсы с этим тегом
    
    def course_count(self, obj):
        return obj.course_set.count()
    course_count.short_description = 'Количество курсов'

@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ('title', 'short_description', 'get_tag')
    search_fields = ('title', 'description')
    
    def get_tag(self, obj):
        return obj.tag.name if obj.tag else 'Нет тега'
    get_tag.short_description = 'Тег'

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
