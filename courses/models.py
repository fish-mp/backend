from django.db import models

from users.models import CustomUser


# Create your models here.

class Files(models.Model):
    file = models.FileField(upload_to='files/')
    title = models.CharField(max_length=100)
    for_teacher = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Файлы'
        verbose_name='Файл'

    def __str__(self):
        return self.title

class Tag(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Course(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    short_description = models.TextField()
    files = models.ManyToManyField(Files)
    image = models.ImageField(upload_to='images/', blank=True, null=True)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    class Meta:
        verbose_name_plural = 'Курсы'
        verbose_name='Курс'

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    state_choices = (
        ('applied', 'Applied'),
        ('enrolled', 'Enrolled'),
        ('rejected', 'Rejected'),
    )

    state = models.CharField(max_length=100, choices=state_choices, default='applied')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = 'Заявки'
        verbose_name='Заявка'