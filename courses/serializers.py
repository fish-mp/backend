from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.fields import SerializerMethodField

from courses.models import Course, Enrollment, Files, Tag


class FileSerializer(ModelSerializer):
    class Meta:
        model = Files
        fields = '__all__'
class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'
class CourseSerializer(ModelSerializer):
    files = SerializerMethodField('get_files')
    tag = TagSerializer(many=False)
    enrollment_state = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = '__all__'

    def get_files(self, obj):
        files = Files.objects.filter(course=obj, for_teacher=False)
        return  FileSerializer(files, many=True).data

    def get_enrollment_state(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return None  # Если пользователь не аутентифицирован, возвращаем None

        try:
            enrollment = Enrollment.objects.get(user=user, course=obj)
            return enrollment.state
        except Enrollment.DoesNotExist:
            return None