from django.db import migrations

SYSTEM_TEMPLATES = [
    {
        "key": "incident_notification",
        "name": "Incident notification",
        "kind": "INCIDENT",
        "description": "Emailed to each guardian when an incident report is sent.",
        "subject": "[[SCHOOL_NAME]] — incident report for [[STUDENT_FIRST_NAME]]",
        "body": (
            "Dear [[GUARDIAN_FULL_NAME]],\n\n"
            "An incident report has been filed for [[STUDENT_FULL_NAME]] regarding "
            "an event on [[INCIDENT_DATE]] ([[INCIDENT_CATEGORY]]).\n\n"
            "Please sign in to Campus to read the full report and acknowledge that "
            "you have seen it. Call [[SCHOOL_ADMIN_NUMBER]] if you have any "
            "questions.\n\n"
            "[[SCHOOL_NAME]]"
        ),
    },
    {
        "key": "report_card_released",
        "name": "Report card released",
        "kind": "REPORT_CARD",
        "description": "Emailed to each guardian when a report card is released.",
        "subject": "[[STUDENT_FIRST_NAME]]'s [[TERM_NAME]] report card is ready",
        "body": (
            "Dear [[GUARDIAN_FULL_NAME]],\n\n"
            "[[STUDENT_FULL_NAME]]'s report card for [[TERM_NAME]] "
            "([[SCHOOL_YEAR]]) has been released. Sign in to Campus to read it.\n\n"
            "Kind regards,\n"
            "[[PRINCIPAL_NAME]]\n"
            "[[SCHOOL_NAME]]"
        ),
    },
    {
        "key": "absence_notification",
        "name": "Absence notification",
        "kind": "ABSENCE",
        "description": "Available for a 'notify guardians' action / daily absence job.",
        "subject": "[[STUDENT_FIRST_NAME]] was marked absent on [[EVENT_DATE]]",
        "body": (
            "Dear [[GUARDIAN_FULL_NAME]],\n\n"
            "[[STUDENT_FULL_NAME]] was reported absent from [[STUDENT_CLASS]] on "
            "[[EVENT_DATE]].\n\n"
            "If this absence was expected, no action is needed. Otherwise, please "
            "call [[SCHOOL_ADMIN_NUMBER]].\n\n"
            "[[SCHOOL_NAME]]"
        ),
    },
    {
        "key": "announcement_email",
        "name": "Announcement email",
        "kind": "ANNOUNCEMENT",
        "description": "Wraps every published announcement sent by email.",
        "subject": "[[SCHOOL_NAME]] — [[ANNOUNCEMENT_TITLE]]",
        "body": (
            "[[ANNOUNCEMENT_BODY]]\n\n"
            "—\n"
            "[[SCHOOL_NAME]]\n"
            "[[SCHOOL_ADDRESS]]\n"
            "[[SCHOOL_PHONE]]"
        ),
    },
]


def seed(apps, schema_editor):
    Template = apps.get_model("communication", "MessageTemplate")
    for spec in SYSTEM_TEMPLATES:
        Template.objects.get_or_create(
            key=spec["key"],
            defaults={**spec, "active": True, "is_system": True},
        )


def unseed(apps, schema_editor):
    Template = apps.get_model("communication", "MessageTemplate")
    Template.objects.filter(
        key__in=[s["key"] for s in SYSTEM_TEMPLATES], is_system=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0002_messagetemplate_alter_outboundemail_kind"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
