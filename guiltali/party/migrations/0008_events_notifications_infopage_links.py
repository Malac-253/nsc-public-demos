import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("party", "0007_postvideo"),
    ]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140)),
                ("date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to="party.membership",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events", to="party.trip",
                    ),
                ),
            ],
            options={"ordering": ["-date", "-created_at"]},
        ),
        migrations.AddField(
            model_name="post",
            name="event",
            field=models.ForeignKey(
                blank=True, help_text="Optional: tag this post (usually a photo/video) to an event.",
                null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="posts", to="party.event",
            ),
        ),
        migrations.AddField(
            model_name="infopage",
            name="link_url",
            field=models.URLField(blank=True, help_text="Optional 'read more' / source link shown at the end of the article."),
        ),
        migrations.AddField(
            model_name="infopage",
            name="link_label",
            field=models.CharField(blank=True, help_text="Button text for link_url, e.g. 'Original recipe'.", max_length=80),
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=240)),
                ("link_path", models.CharField(blank=True, max_length=200)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to="party.membership",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications", to="party.membership",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications", to="party.trip",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
