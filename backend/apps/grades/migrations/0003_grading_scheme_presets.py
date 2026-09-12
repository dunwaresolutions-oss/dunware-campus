# Seeds four real, sourced grading-scheme presets so every install - demo or
# a genuine customer - has real starting points to choose from instead of a
# blank slate. None is activated here (see seed_demo.py for the demo school
# activating one, and GradingSchemeViewSet.activate for how a real customer
# picks theirs). Sourced from Global_K12_School_Grading_Standards (2026-09):
# Ontario's elementary 4-level scale and South Africa's NCS 7-point scale
# are well-documented public standards, independently verifiable; the
# Bahamas GPA table and Botswana bands are presented as given in that
# reference and are internally consistent, but not independently
# fact-checked line-by-line the way the first two were.

from django.db import migrations


def _seed_presets(apps, schema_editor):
    GradingScheme = apps.get_model("grades", "GradingScheme")
    GradeBand = apps.get_model("grades", "GradeBand")

    presets = [
        {
            "name": "Bahamas — 4.0 GPA",
            "description": "Letter grades on a cumulative 4.0 grade-point scale, as used by "
                            "Bahamian secondary schools for internal continuous reporting.",
            "uses_gpa": True,
            "gpa_scale": "4.00",
            "bands": [
                ("A", 90, 100, "4.00", "Excellent / Outstanding performance"),
                ("A-", 85, 89.99, "3.75", "Very Good progress"),
                ("B+", 80, 84.99, "3.50", "Above Average attainment"),
                ("B", 75, 79.99, "3.00", "Good / Satisfactory status"),
                ("B-", 70, 74.99, "2.75", "Competent framework execution"),
                ("C+", 65, 69.99, "2.50", "Above Average Pass status"),
                ("C", 60, 64.99, "2.00", "Average Pass benchmark"),
                ("C-", 55, 59.99, "1.75", "Below Average Pass status"),
                ("D", 50, 54.99, "1.00", "Minimally Acceptable / Weak Pass"),
                ("F", 0, 49.99, "0.00", "Failing / No credit issued"),
            ],
        },
        {
            "name": "Ontario — Elementary (Grades 1-8)",
            "description": "The four-level provincial achievement scale (Growing Success), "
                            "not a GPA — used for elementary/middle report cards, not high school.",
            "uses_gpa": False,
            "gpa_scale": None,
            "bands": [
                ("Level 4", 80, 100, None, "Exceeds the provincial standard"),
                ("Level 3", 70, 79.99, None, "Meets the provincial standard"),
                ("Level 2", 60, 69.99, None, "Approaching the provincial standard"),
                ("Level 1", 50, 59.99, None, "Well below the provincial standard"),
                ("R", 0, 49.99, None, "Remedial — insufficient to demonstrate mastery"),
            ],
        },
        {
            "name": "South Africa — NCS 7-point",
            "description": "The 7-code achievement scale mandated by the National Curriculum "
                            "Statement (CAPS) for term reporting.",
            "uses_gpa": False,
            "gpa_scale": None,
            "bands": [
                ("7", 80, 100, None, "Outstanding achievement"),
                ("6", 70, 79.99, None, "Meritorious achievement"),
                ("5", 60, 69.99, None, "Substantial achievement"),
                ("4", 50, 59.99, None, "Adequate achievement"),
                ("3", 40, 49.99, None, "Moderate achievement"),
                ("2", 30, 39.99, None, "Elementary achievement"),
                ("1", 0, 29.99, None, "Not achieved"),
            ],
        },
        {
            "name": "Botswana — Letter bands",
            "description": "Percentage-to-letter mapping used for term reporting in Botswana "
                            "primary and secondary institutions.",
            "uses_gpa": False,
            "gpa_scale": None,
            "bands": [
                ("A", 80, 100, None, "Distinction / Outstanding mastery"),
                ("B", 70, 79.99, None, "Very Good / Meritorious progression"),
                ("C", 60, 69.99, None, "Credit / Good standard level competency"),
                ("D", 50, 59.99, None, "Pass / Satisfactory baseline execution"),
                ("E", 40, 49.99, None, "Weak Pass / Marginal term tracking"),
                ("F", 0, 39.99, None, "Fail"),
            ],
        },
    ]

    for p in presets:
        scheme = GradingScheme.objects.create(
            name=p["name"], description=p["description"],
            uses_gpa=p["uses_gpa"], gpa_scale=p["gpa_scale"], is_active=False,
        )
        for order, (label, lo, hi, points, desc) in enumerate(p["bands"], start=1):
            GradeBand.objects.create(
                scheme=scheme, label=label, min_percent=lo, max_percent=hi,
                gpa_points=points, description=desc, order=order,
            )


def _remove_presets(apps, schema_editor):
    GradingScheme = apps.get_model("grades", "GradingScheme")
    GradingScheme.objects.filter(name__in=[
        "Bahamas — 4.0 GPA",
        "Ontario — Elementary (Grades 1-8)",
        "South Africa — NCS 7-point",
        "Botswana — Letter bands",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0002_gradingscheme_reportcard_cumulative_gpa_and_more'),
    ]

    operations = [
        migrations.RunPython(_seed_presets, _remove_presets),
    ]
