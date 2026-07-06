from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("party", "0008_events_notifications_infopage_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="opens_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When a scheduled poll goes live on the feed.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="poll",
            name="repeat_daily",
            field=models.BooleanField(
                default=False,
                help_text="After publishing, queue the same poll for the next day at this time.",
            ),
        ),
        migrations.CreateModel(
            name="PostLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("link_url", models.URLField(blank=True)),
                ("internal_path", models.CharField(blank=True, max_length=200)),
                ("label", models.CharField(default="Open link", max_length=80)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="links",
                        to="party.post",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
    ]
