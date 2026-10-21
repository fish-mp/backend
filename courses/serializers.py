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
        courses = obj.courses.filter(is_popular=True)
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
    modules = CourseModuleSerializer(many=True, read_only=True)
    enrollment_state = serializers.SerializerMethodField('get_enrollment_state')

    class Meta:
        model = Course
        fields = '__all__'

    def get_files(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        if user.is_staff or user.is_superuser:
            files = Files.objects.filter(course=obj)
        else:
            files = Files.objects.filter(course=obj, for_teacher=False)
        return FileSerializer(files, many=True).data

    def get_enrollment_state(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            enrollment = Enrollment.objects.get(user=request.user, course=obj)
            return enrollment.state
        except Enrollment.DoesNotExist:
            return None


class UserEnrollmentSerializer(ModelSerializer):
    course = CourseSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ['id', 'course', 'state', 'created_at']