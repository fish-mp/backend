from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.fields import SerializerMethodField
from courses.models import Course, Enrollment, Files, Tag, School, Teacher, CourseModule


class FileSerializer(ModelSerializer):
    class Meta:
        model = Files
        fields = '__all__'


class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class SchoolSerializer(ModelSerializer):
    class Meta:
        model = School
        fields = ['id', 'title', 'subtitle', 'slug', 'order']


class TeacherSerializer(ModelSerializer):
    school_title = serializers.CharField(source='school.title', read_only=True)
    school_slug = serializers.CharField(source='school.slug', read_only=True)

    class Meta:
        model = Teacher
        fields = ['id', 'full_name', 'photo', 'school', 'school_title', 'school_slug', 'order']


class CourseCardSerializer(ModelSerializer):
    school_slug = serializers.CharField(source='school.slug', read_only=True)

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'image', 'is_free', 'course_type',
            'academic_hours', 'school_slug'
        ]


class SchoolWithPopularCoursesSerializer(ModelSerializer):
    popular_courses = SerializerMethodField()

    class Meta:
        model = School
        fields = ['id', 'title', 'subtitle', 'slug', 'order', 'popular_courses']

    def get_popular_courses(self, obj):
        courses = obj.popular_courses
        return CourseCardSerializer(courses, many=True, context=self.context).data


class CourseModuleSerializer(ModelSerializer):
    module_type_display = serializers.CharField(source='get_module_type_display', read_only=True)

    class Meta:
        model = CourseModule
        fields = ['id', 'title', 'module_type', 'module_type_display', 'content', 'order']


class CourseSerializer(ModelSerializer):
    files = SerializerMethodField('get_files')
    tag = TagSerializer(many=False, read_only=True)
    school_details = SchoolSerializer(source='school', read_only=True)
    modules = SerializerMethodField()
    enrollment_state = serializers.SerializerMethodField('get_enrollment_state')

    class Meta:
        model = Course
        fields = '__all__'

    def get_files(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        if not (user.is_staff or user.is_superuser or self.get_enrollment_state(obj) == 'enrolled'):
            return []
        files = [file for file in obj.files.all() if user.is_staff or user.is_superuser or not file.for_teacher]
        return FileSerializer(files, many=True).data

    def get_modules(self, obj):
        request = self.context.get('request')
        can_read = bool(request and request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser or self.get_enrollment_state(obj) == 'enrolled'))
        data = CourseModuleSerializer(obj.modules.all(), many=True).data
        for module in data:
            if not can_read and module['module_type'] not in ['intro', 'program']:
                module['content'] = ''
        return data

    def get_enrollment_state(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        enrollments = getattr(obj, 'user_enrollments', None)
        if enrollments is None:
            enrollments = list(Enrollment.objects.filter(user=request.user, course=obj))
        return enrollments[0].state if enrollments else None


class UserEnrollmentSerializer(ModelSerializer):
    course = CourseSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ['id', 'course', 'state', 'created_at']
