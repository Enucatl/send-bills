# Generated by Django 5.2.3 on 2025-07-04 14:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bills", "0004_remove_recurringbill_additional_information_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bill",
            name="currency",
            field=models.CharField(
                choices=[("CHF", "CHF"), ("EUR", "EUR")], default="CHF", max_length=3
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="bill",
            name="language",
            field=models.CharField(
                choices=[("en", "en"), ("de", "de"), ("fr", "fr"), ("it", "it")],
                default="en",
                max_length=2,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="bill",
            name="sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recurringbill",
            name="currency",
            field=models.CharField(
                choices=[("CHF", "CHF"), ("EUR", "EUR")], default="CHF", max_length=3
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringbill",
            name="language",
            field=models.CharField(
                choices=[("en", "en"), ("de", "de"), ("fr", "fr"), ("it", "it")],
                default="en",
                max_length=2,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="contact",
            name="name",
            field=models.CharField(max_length=70),
        ),
        migrations.AlterField(
            model_name="creditor",
            name="city",
            field=models.CharField(max_length=35),
        ),
        migrations.AlterField(
            model_name="creditor",
            name="name",
            field=models.CharField(max_length=70),
        ),
        migrations.AlterField(
            model_name="creditor",
            name="pcode",
            field=models.CharField(max_length=16),
        ),
    ]
