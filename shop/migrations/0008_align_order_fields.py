from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('shop', '0007_cart_constraints')]
    operations = [
        migrations.AlterField(model_name='order', name='email', field=models.EmailField(blank=True, max_length=254, verbose_name='Email для чека')),
        migrations.AlterField(model_name='order', name='phone', field=models.CharField(blank=True, max_length=20, verbose_name='Телефон')),
        migrations.AlterField(model_name='order', name='city', field=models.CharField(blank=True, max_length=100, verbose_name='Город')),
        migrations.AlterField(model_name='order', name='street', field=models.CharField(blank=True, max_length=150, verbose_name='Улица')),
        migrations.AlterField(model_name='order', name='house', field=models.CharField(blank=True, max_length=30, verbose_name='Дом')),
        migrations.AlterField(model_name='order', name='apartment', field=models.CharField(blank=True, max_length=30, verbose_name='Квартира')),
        migrations.AlterField(model_name='order', name='postal_code', field=models.CharField(blank=True, max_length=20, verbose_name='Индекс')),
    ]
