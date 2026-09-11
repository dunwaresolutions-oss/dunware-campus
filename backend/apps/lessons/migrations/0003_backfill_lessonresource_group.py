from django.db import migrations


def fill(apps, schema_editor):
    LessonResource = apps.get_model("lessons", "LessonResource")
    qs = LessonResource.objects.filter(group__isnull=True, lesson__isnull=False)
    for resource in qs.select_related("lesson"):
        resource.group_id = resource.lesson.group_id
        resource.save(update_fields=["group"])


class Migration(migrations.Migration):
    dependencies = [
        ("lessons", "0002_lessonresource_group"),
    ]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
