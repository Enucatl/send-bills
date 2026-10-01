from django.db import migrations


def reconcile_paid_bills(apps, schema_editor) -> None:
    """Honor recorded payment dates without changing issued references."""
    Bill = apps.get_model("bills", "Bill")
    Bill.objects.using(schema_editor.connection.alias).filter(
        paid_at__isnull=False
    ).exclude(status="paid").update(status="paid")


class Migration(migrations.Migration):
    """Repair historical payment status without inventing payment dates."""

    dependencies = [("bills", "0010_creditor_house_num_creditor_street")]

    operations = [
        migrations.RunPython(reconcile_paid_bills, migrations.RunPython.noop),
    ]
