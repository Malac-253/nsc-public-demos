from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("party", "0005_expense_split_adjust"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="row_color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional hex color for the expense table row.",
                max_length=9,
            ),
        ),
        migrations.AddField(
            model_name="post",
            name="archived",
            field=models.BooleanField(default=False),
        ),
    ]
