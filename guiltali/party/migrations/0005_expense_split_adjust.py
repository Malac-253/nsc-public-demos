from django.db import migrations, models


def rooms_to_equal(apps, schema_editor):
    Expense = apps.get_model("party", "Expense")
    Expense.objects.filter(split_method="rooms").update(split_method="equal")


class Migration(migrations.Migration):

    dependencies = [
        ("party", "0004_infopage_created_at_infopage_created_by_and_more"),
    ]

    operations = [
        migrations.RunPython(rooms_to_equal, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="expense",
            name="split_method",
            field=models.CharField(
                choices=[
                    ("equal", "Split equally"),
                    ("percent", "Split by percentages"),
                    ("shares", "Split by shares"),
                    ("present", "Split by nights present"),
                    ("custom", "Exact amounts"),
                    ("adjust", "Split with adjustments"),
                ],
                default="equal",
                max_length=16,
            ),
        ),
    ]
