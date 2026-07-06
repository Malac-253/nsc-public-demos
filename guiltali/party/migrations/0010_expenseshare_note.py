from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("party", "0009_postlink_poll_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="expenseshare",
            name="note",
            field=models.CharField(
                blank=True,
                help_text="Plain-language note for this person on this expense (shown on their receipt).",
                max_length=300,
            ),
        ),
    ]
