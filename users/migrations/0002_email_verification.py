from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def normalize_existing_users(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    users = User.objects.using(schema_editor.connection.alias)
    duplicates = users.annotate(normalized=Lower('email')).values('normalized').annotate(n=Count('pk')).filter(n__gt=1)
    if duplicates.exists():
        raise RuntimeError('Email addresses differing only by case exist. Resolve duplicates before migrating; no accounts were merged.')
    users.update(email=Lower('email'))
    # Preserve access to existing administration accounts. Customers use resend.
    users.filter(is_staff=True).update(is_email_verified=True)


class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]
    operations = [
        migrations.AddField(model_name='customuser', name='is_email_verified',
                            field=models.BooleanField(default=False, verbose_name='Почта подтверждена')),
        migrations.RunPython(normalize_existing_users, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='customuser',
            constraint=models.UniqueConstraint(Lower('email'), name='users_email_ci_unique')),
    ]
