import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0001_initial"),
        ("lessons", "0003_backfill_lessonresource_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lessonresource",
            name="group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lesson_resources",
                to="people.group",
                help_text="Who this is for. Auto-filled from the lesson plan when one is set.",
            ),
        ),
    ]
