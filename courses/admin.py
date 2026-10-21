from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from courses.models import Course, Enrollment, Files, Tag, School, Teacher, CourseModule

class CourseModuleInline(TabularInline):
    model = CourseModule
    extra = 0

@admin.register(School)
class SchoolAdmin(ModelAdmin):
    list_display = ('title', 'subtitle', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'subtitle')
    prepopulated_fields = {'slug': ('title',)}

@admin.register(Teacher)
class TeacherAdmin(ModelAdmin):
    list_display = ('full_name', 'school', 'order', 'photo_preview')
    list_filter = ('school',)
    list_editable = ('order',)

    def photo_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" style="height: 45px; width: 45px; object-fit: cover; border-radius: 50%;"/>', obj.photo.url)
        return "Нет фото"
    photo_preview.short_description = "Фото"

@admin.register(Tag)
class TagAdmin(ModelAdmin):
    list_display = ('name', 'course_count')
    def course_count(self, obj):
        return obj.course_set.count()

@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ('title', 'school', 'course_type', 'academic_hours', 'is_free', 'is_popular')
    list_filter = ('school', 'course_type', 'is_free', 'is_popular')
    list_editable = ('is_free', 'is_popular')
    search_fields = ('title',)
    inlines = [CourseModuleInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('school', 'title', 'course_type', 'tag', 'is_free', 'is_popular')
        }),
        ('Специфика ДПО', {
            'fields': ('academic_hours', 'license_file', 'accreditation_file', 'certificate_sample'),
            'classes': ('collapse',),
            'description': 'Заполняйте только для курсов повышения квалификации и переподготовки.'
        }),
        ('Контент', {
            'fields': ('description', 'short_description', 'image', 'files')
        }),
    )

@admin.register(Files)
class FilesAdmin(ModelAdmin):
    list_display = ('title', 'file', 'for_teacher')

@admin.register(Enrollment)
class EnrollmentAdmin(ModelAdmin):
    list_display = ('user', 'course', 'state', 'created_at')