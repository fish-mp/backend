from django.db import migrations, models
from django.db.models import Count, Sum


def merge_duplicates(apps, schema_editor):
    Item = apps.get_model('shop', 'CartItem')
    items = Item.objects.using(schema_editor.connection.alias)
    items.filter(quantity__lt=1).delete()
    groups = items.values('cart_id', 'product_id').annotate(n=Count('id'), quantity_sum=Sum('quantity')).filter(n__gt=1)
    for group in list(groups):
        rows = items.filter(cart_id=group['cart_id'], product_id=group['product_id']).order_by('pk')
        keeper = rows.first()
        rows.exclude(pk=keeper.pk).delete()
        items.filter(pk=keeper.pk).update(quantity=group['quantity_sum'])


class Migration(migrations.Migration):
    dependencies = [('shop', '0006_order_contact_and_delivery_fields')]
    operations = [
        migrations.RunPython(merge_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='cartitem', constraint=models.UniqueConstraint(fields=('cart', 'product'), name='unique_cart_product')),
        migrations.AddConstraint(model_name='cartitem', constraint=models.CheckConstraint(condition=models.Q(quantity__gte=1), name='cart_quantity_positive')),
    ]
