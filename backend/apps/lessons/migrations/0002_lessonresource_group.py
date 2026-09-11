import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0001_initial"),
        ("lessons", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lessonresource",
            name="group",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lesson_resources",
                to="people.group",
                help_text="Who this is for. Auto-filled from the lesson plan when one is set.",
            ),
        ),
        migrations.AlterField(
            model_name="lessonresource",
            name="lesson",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resources",
                to="lessons.lessonplan",
                help_text="Optional — leave blank for a resource that isn't tied to one dated lesson.",
            ),
        ),
        migrations.AddIndex(
            model_name="lessonresource",
            index=models.Index(fields=["group"], name="lessons_les_group_i_aaf684_idx"),
        ),
    ]
