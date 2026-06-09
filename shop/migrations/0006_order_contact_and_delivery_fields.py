from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0005_alter_color_options_order_payment_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='email',
            field=models.EmailField(default='', max_length=254, verbose_name='Email для чека'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='phone',
            field=models.CharField(default='', max_length=20, verbose_name='Телефон'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='city',
            field=models.CharField(default='', max_length=100, verbose_name='Город'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='street',
            field=models.CharField(default='', max_length=150, verbose_name='Улица'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='house',
            field=models.CharField(default='', max_length=30, verbose_name='Дом'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='apartment',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Квартира'),
        ),
        migrations.AddField(
            model_name='order',
            name='postal_code',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Индекс'),
        ),
        migrations.AddField(
            model_name='order',
            name='offer_accepted',
            field=models.BooleanField(default=False, verbose_name='Согласие с публичной офертой'),
        ),
    ]
