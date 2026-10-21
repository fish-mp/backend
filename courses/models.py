from django.db import models
from users.models import CustomUser


class School(models.Model):
    """Раздел учебной платформы"""
    title = models.CharField(max_length=150, verbose_name="Название раздела (напр. ДПО)")
    subtitle = models.CharField(max_length=150, blank=True, verbose_name="Подзаголовок (напр. Для взрослых)")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок (ДПО = 1)")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = 'Раздел'
        verbose_name_plural = 'Разделы'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title


class Teacher(models.Model):
    full_name = models.CharField(max_length=150, verbose_name="Имя и Фамилия")
    photo = models.ImageField(upload_to='teachers/', blank=True, null=True, verbose_name="Фотография")
    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True, related_name='teachers',
                               verbose_name="Раздел")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок отображения")

    class Meta:
        verbose_name = 'Преподаватель'
        verbose_name_plural = 'Преподаватели'
        ordering = ['order', 'id']

    def __str__(self):
        return self.full_name


class Files(models.Model):
    file = models.FileField(upload_to='files/')
    title = models.CharField(max_length=100)
    for_teacher = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Файлы'
        verbose_name = 'Файл'

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'

    def __str__(self):
        return self.name


class Course(models.Model):
    COURSE_TYPES = (
        ('standard', 'Обычный курс/кружок'),
        ('qualification', 'Повышение квалификации (ДПО)'),
        ('retraining', 'Переподготовка (ДПО)'),
    )

    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses',
                               verbose_name="Раздел")
    title = models.CharField(max_length=200, verbose_name="Название курса")
    course_type = models.CharField(max_length=50, choices=COURSE_TYPES, default='standard', verbose_name="Тип курса")

    # Специфичные поля для ДПО
    academic_hours = models.PositiveIntegerField(blank=True, null=True, verbose_name="Академ. часы")
    license_file = models.FileField(upload_to='dpo/licenses/', blank=True, null=True, verbose_name="Лицензия (Файл)")
    accreditation_file = models.FileField(upload_to='dpo/accreditations/', blank=True, null=True,
                                          verbose_name="Аккредитация (Файл)")
    certificate_sample = models.ImageField(upload_to='dpo/certificates/', blank=True, null=True,
                                           verbose_name="Образец документа")

    # Базовые поля
    description = models.TextField(verbose_name="Полное описание")
    short_description = models.TextField(blank=True, verbose_name="Краткое описание")
    image = models.ImageField(upload_to='images/', blank=True, null=True, verbose_name="Обложка курса")
    files = models.ManyToManyField(Files, blank=True, verbose_name="Доп. файлы курса")
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Тег")

    is_free = models.BooleanField(default=True, verbose_name="Бесплатный курс")
    is_popular = models.BooleanField(default=True, verbose_name="Показывать в популярных на главной")

    class Meta:
        verbose_name_plural = 'Курсы'
        verbose_name = 'Курс'

    def __str__(self):
        return f"{self.title} ({self.get_course_type_display()})"


class CourseModule(models.Model):
    MODULE_TYPES = (
        ('intro', 'Введение в курс'),
        ('program', 'Программа'),
        ('lecture', 'Лекция'),
        ('practice', 'Практика'),
        ('test', 'Тест'),
        ('final', 'Итоговая работа'),
    )

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name="Курс")
    title = models.CharField(max_length=200, verbose_name="Название модуля/темы")
    module_type = models.CharField(max_length=50, choices=MODULE_TYPES, default='lecture', verbose_name="Тип элемента")
    content = models.TextField(blank=True, verbose_name="Текст/Описание")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок прохождения")

    class Meta:
        verbose_name = 'Элемент учебного плана'
        verbose_name_plural = 'Учебный план (Модули)'
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.get_module_type_display()}: {self.title}"


class Enrollment(models.Model):
    state_choices = (
        ('applied', 'Applied'),
        ('enrolled', 'Enrolled'),
        ('rejected', 'Rejected'),
    )

    state = models.CharField(max_length=100, choices=state_choices, default='enrolled')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Заявки'
        verbose_name = 'Заявка'