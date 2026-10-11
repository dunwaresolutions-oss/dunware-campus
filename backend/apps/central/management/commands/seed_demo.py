"""
Synthetic multi-school demo dataset for Campus Central.

Every record is invented; it NEVER contains a real student, family or staff
member (same rule as Campus's own seed_demo). Refuses to run under
production settings unless --force is given.

Why this exists: Damien is linking one REAL Campus install to this Central
instance by hand (the actual `link_central` / "Campus — Central Link Setup"
/ real sync path), to get a definitive, live answer on whether the whole
sync mechanism actually works end to end. That real link will only ever
produce ONE school's worth of data. Central's entire value proposition is
being a Ministry's cross-school view, so testing the console (dashboard,
by-district toggle, search, school registry) against a single school looks
thin and proves nothing about multi-school behaviour. This command seeds
several ADDITIONAL, clearly-synthetic schools directly into Central's own
database -- bypassing the real sync protocol entirely (there is no second
real Campus install to sync from) -- so the console has a realistic,
multi-district dataset to look at alongside Damien's one real linked school.

Every seeded school's name starts with "Demo — " specifically so it is
never confusable with a real linked school in the UI, and so --flush can
safely delete only ITS OWN rows without ever touching a real School that
Damien has registered and linked for the real test.

    manage_central.py seed_demo --force                  # 6 schools, default sizes
    manage_central.py seed_demo --force --schools 10      # a bigger ministry
    manage_central.py seed_demo --quick --force           # tiny fast build
    manage_central.py seed_demo --force --flush           # replace the demo set cleanly
"""
from __future__ import annotations

import datetime as dt
import random
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.central.models import (
    CentralAttendanceSummary,
    CentralBillingSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralIncidentSummary,
    CentralRegistrationCounts,
    CentralReportCard,
    CentralStaff,
    CentralStudent,
    School,
    SnapshotBatch,
)

DEMO_PREFIX = "Demo — "

# ── name pools (same Bahamian-leaning, invented flavour as Campus's own
#    seed_demo, kept small and self-contained -- apps.central can't import
#    Campus's seed_demo module, since it pulls in apps.people / apps.billing
#    / etc., none of which are installed in Central's own project). ────────
FIRST = [
    "Aaliyah", "Amari", "Anaya", "Andre", "Ava", "Brianna", "Caleb", "Chloe",
    "Daniel", "David", "Deja", "Denzel", "Elijah", "Ella", "Ethan", "Gabriel",
    "Grace", "Imani", "Isaiah", "Jaden", "Jayla", "Jerome", "Josiah", "Kayla",
    "Keanu", "Kian", "Layla", "Leah", "Liam", "Makayla", "Malik", "Maya",
    "Micah", "Nathan", "Nia", "Noah", "Olivia", "Omari", "Rhea", "Sade",
    "Samuel", "Sasha", "Shania", "Theo", "Trey", "Zara", "Zion",
]
LAST = [
    "Adderley", "Bain", "Bethel", "Bowe", "Cartwright", "Cash", "Charlton",
    "Clarke", "Curry", "Darville", "Deveaux", "Dorsett", "Farrington",
    "Ferguson", "Forbes", "Gibson", "Hanna", "Higgs", "Johnson", "Knowles",
    "Lightbourne", "Major", "McKenzie", "Miller", "Moss", "Munroe", "Newbold",
    "Nixon", "Pinder", "Poitier", "Pratt", "Rahming", "Roberts", "Rolle",
    "Russell", "Sands", "Saunders", "Seymour", "Smith", "Stubbs", "Sweeting",
    "Taylor", "Thompson", "Turnquest", "Williams", "Wilson",
]
GUARDIAN_FIRST = [
    "Patrice", "Shantelle", "Andrea", "Monique", "Verona", "Delores",
    "Anthony", "Kendal", "Wellington", "Godfrey", "Cyril", "Rupert",
    "Patricia", "Sharon", "Cheryl", "Donna", "Winston", "Clement",
]
SCHOOL_NAMES = [
    ("Windward Cay Primary", "New Providence"),
    ("Harbour View Academy", "New Providence"),
    ("Seaside Preparatory", "Grand Bahama"),
    ("Coral Reef Primary", "Grand Bahama"),
    ("Hope Town All-Age", "Abaco"),
    ("Marsh Harbour Primary", "Abaco"),
    ("Governor's Harbour Primary", "Eleuthera"),
    ("Rock Sound All-Age", "Eleuthera"),
    ("George Town Primary", "Exuma"),
    ("Fresh Creek All-Age", "Andros"),
]
GROUP_KINDS = ["CLASS", "SECTION"]
STAFF_ROLE_POOL = [Role.ADMIN, Role.FRONT_DESK, Role.TEACHER, Role.TUTOR]
RELATIONSHIPS = ["MOTHER", "FATHER", "GUARDIAN"]
CONSENT_KINDS = ["PHOTO_RELEASE", "FIELD_TRIP", "DATA_SHARING"]
INCIDENT_CATEGORIES = ["BEHAVIOUR", "SAFETY", "BULLYING", "MEDICAL", "PROPERTY"]
INCIDENT_STATUSES = ["OPEN", "RESOLVED", "ESCALATED"]
REPORT_CARD_STATUSES = ["DRAFT", "FINALIZED", "RELEASED"]
TERM_NAME = "Term 1 (2026-2027)"


def _term_source_id(school_name: str) -> uuid.UUID:
    """Deterministic per-school UUID standing in for a real Term row's own
    id -- Central has no Term model of its own, only the source_id a school
    would have sent."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"centraldemo.term.{school_name}")


class Command(BaseCommand):
    help = "Load a synthetic multi-school demo dataset directly into Campus Central."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schools", type=int, default=6,
            help="How many synthetic schools to create (max 10 - the name pool's size).",
        )
        parser.add_argument(
            "--quick", action="store_true",
            help="Tiny fast build: 2 schools, ~15 students each.",
        )
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete every previously-seeded 'Demo — ' school first (and only those - "
                 "a real, genuinely-linked school's name never starts with that prefix, so "
                 "it is never touched).",
        )
        parser.add_argument("--seed", type=int, default=1729)
        parser.add_argument("--force", action="store_true",
                             help="Allow running even when DEBUG is False")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed with DEBUG=False. Pass --force if you mean it.")

        rng = random.Random(options["seed"])  # nosec B311 - synthetic data, not a security context
        with transaction.atomic():
            if options["flush"]:
                removed, _ = School.objects.filter(name__startswith=DEMO_PREFIX).delete()
                self.stdout.write(f"flushed previous demo schools (and their rows): {removed}")
            summary = self._seed(rng, options)
        for k, v in summary.items():
            self.stdout.write(f"{k:>24}: {v}")
        self.stdout.write(self.style.SUCCESS("Central demo data loaded"))

    def _seed(self, rng, opts):
        quick = opts["quick"]
        n_schools = 2 if quick else max(1, min(opts["schools"], len(SCHOOL_NAMES)))
        pool = SCHOOL_NAMES[:n_schools]

        made = {
            "schools": 0, "students": 0, "guardians": 0, "staff": 0, "groups": 0,
            "enrolments": 0, "consents": 0, "report_cards": 0,
            "attendance_summaries": 0, "incident_summaries": 0, "billing_summaries": 0,
            "registration_counts": 0, "snapshot_batches": 0,
        }

        for name, district in pool:
            full_name = f"{DEMO_PREFIX}{name}"
            # idempotent: re-running without --flush just refreshes this one school
            School.objects.filter(name=full_name).delete()
            slug = name.lower().replace(" ", "").replace(chr(39), "")
            school = School.objects.create(
                name=full_name, district=district,
                contact_email=f"office@{slug}.centraldemo.example",
                active=True,
                sync_status=School.SyncStatus.OK,
                last_synced_at=timezone.now() - dt.timedelta(hours=rng.randint(1, 20)),
                snapshot_schema_version=1,
            )
            made["schools"] += 1
            term_id = _term_source_id(full_name)

            n_students = (12 if quick else rng.randint(60, 220))
            n_groups = max(1, -(-n_students // 28))
            groups = []
            for gi in range(n_groups):
                grp = CentralGroup.objects.create(
                    school=school, source_id=uuid.uuid4(),
                    name=f"Grade {1 + gi // 2}{'AB'[gi % 2]}",
                    kind=rng.choice(GROUP_KINDS),
                    stage_label=f"Grade {1 + gi // 2}",
                    capacity=30, active=True, live_count=0,
                    source_updated_at=timezone.now(),
                )
                groups.append(grp)
            made["groups"] += len(groups)

            # staff: one admin, one front desk, a handful of teachers/tutors
            staff_rows = [
                CentralStaff(
                    school=school, source_id=uuid.uuid4(),
                    username=f"{name.lower().split()[0]}.admin", role=Role.ADMIN, active=True,
                ),
                CentralStaff(
                    school=school, source_id=uuid.uuid4(),
                    username=f"{name.lower().split()[0]}.frontdesk", role=Role.FRONT_DESK,
                    active=True,
                ),
            ]
            n_staff_extra = 3 if quick else max(4, n_students // 18)
            for si in range(n_staff_extra):
                staff_rows.append(CentralStaff(
                    school=school, source_id=uuid.uuid4(),
                    username=f"staff{si}.{name.lower().split()[0]}",
                    role=rng.choice(STAFF_ROLE_POOL), active=rng.random() > 0.05,
                ))
            CentralStaff.objects.bulk_create(staff_rows)
            made["staff"] += len(staff_rows)

            # families: 1-3 siblings sharing a surname + guardian(s)
            students: list[CentralStudent] = []
            attendance_rows: list[CentralAttendanceSummary] = []
            consent_rows: list[CentralConsent] = []
            report_card_rows: list[CentralReportCard] = []
            remaining = n_students
            while remaining > 0:
                family_size = min(remaining, rng.choice([1, 1, 1, 2, 2, 3]))
                last = rng.choice(LAST)
                family_students: list[CentralStudent] = []
                for _ in range(family_size):
                    grp = rng.choice(groups)
                    status = rng.choices(
                        ["ACTIVE", "INACTIVE", "WITHDRAWN"], weights=[92, 5, 3], k=1
                    )[0]
                    student = CentralStudent.objects.create(
                        school=school, source_id=uuid.uuid4(),
                        first_name=rng.choice(FIRST), last_name=last,
                        date_of_birth=dt.date(2012, 1, 1) + dt.timedelta(days=rng.randint(0, 5400)),
                        student_number=f"{rng.randint(100000, 999999)}",
                        status=status,
                        primary_group_source_id=grp.source_id,
                        guardian_count=0,
                        source_updated_at=timezone.now(),
                    )
                    grp.live_count += 1 if status == "ACTIVE" else 0
                    family_students.append(student)
                    students.append(student)

                    present = rng.randint(140, 175)
                    absent = rng.randint(0, 12)
                    late = rng.randint(0, 8)
                    total = present + absent + late
                    attendance_rows.append(CentralAttendanceSummary(
                        school=school, student_source_id=student.source_id,
                        term_source_id=term_id, present=present, absent=absent, late=late,
                        present_pct=round(100 * present / total, 1) if total else None,
                    ))
                    for kind in rng.sample(CONSENT_KINDS, k=rng.randint(1, len(CONSENT_KINDS))):
                        consent_rows.append(CentralConsent(
                            school=school, source_id=uuid.uuid4(),
                            student_source_id=student.source_id, kind=kind, version="1.0",
                            granted=rng.random() > 0.08,
                            recorded_at=timezone.now() - dt.timedelta(days=rng.randint(10, 300)),
                        ))
                    report_card_rows.append(CentralReportCard(
                        school=school, source_id=uuid.uuid4(),
                        student_source_id=student.source_id, term_source_id=term_id,
                        status=rng.choices(
                            REPORT_CARD_STATUSES, weights=[10, 20, 70], k=1
                        )[0],
                    ))

                n_guardians = 1 if (family_size == 1 and rng.random() < 0.6) else 2
                children_payload = [
                    {"student_id": str(s.source_id), "relationship": rng.choice(RELATIONSHIPS)}
                    for s in family_students
                ]
                for _ in range(n_guardians):
                    CentralGuardian.objects.create(
                        school=school, source_id=uuid.uuid4(),
                        first_name=rng.choice(GUARDIAN_FIRST), last_name=last,
                        email=f"{last.lower()}{rng.randint(1,999)}@centraldemo.example",
                        phone=f"(242) 555-0{rng.randint(100, 999)}",
                        children=children_payload,
                    )
                    made["guardians"] += 1
                for s in family_students:
                    s.guardian_count = n_guardians
                    s.save(update_fields=["guardian_count"])

                remaining -= family_size
            made["students"] += len(students)

            CentralGroup.objects.bulk_update(groups, ["live_count"])
            CentralAttendanceSummary.objects.bulk_create(attendance_rows, batch_size=1000)
            made["attendance_summaries"] += len(attendance_rows)
            CentralConsent.objects.bulk_create(consent_rows, batch_size=1000)
            made["consents"] += len(consent_rows)
            CentralReportCard.objects.bulk_create(report_card_rows, batch_size=1000)
            made["report_cards"] += len(report_card_rows)

            # enrolments: every active/inactive student enrolled in its own group
            enrolment_rows = [
                CentralEnrolment(
                    school=school, source_id=uuid.uuid4(),
                    student_source_id=s.source_id, group_source_id=s.primary_group_source_id,
                    start_date=dt.date(2026, 8, 31),
                    end_date=None if s.status == "ACTIVE" else timezone.localdate(),
                    status="ACTIVE" if s.status == "ACTIVE" else "ENDED",
                    source_updated_at=timezone.now(),
                )
                for s in students
            ]
            CentralEnrolment.objects.bulk_create(enrolment_rows, batch_size=1000)
            made["enrolments"] += len(enrolment_rows)

            # registration counts (aggregate, one row per school)
            CentralRegistrationCounts.objects.update_or_create(
                school=school,
                defaults={
                    "applications_by_status": {
                        "SUBMITTED": rng.randint(3, 20),
                        "UNDER_REVIEW": rng.randint(1, 10),
                        "WAITLISTED": rng.randint(0, 8),
                        "OFFERED": rng.randint(0, 6),
                    },
                    "waitlist_by_group": {
                        grp.name: rng.randint(0, 5) for grp in rng.sample(
                            groups, k=min(3, len(groups))
                        )
                    },
                },
            )
            made["registration_counts"] += 1

            # incident summary: a handful of category/severity/status combos
            seen_combos = set()
            incident_rows = []
            for _ in range(3 if quick else 10):
                combo = (
                    rng.choice(INCIDENT_CATEGORIES), rng.randint(1, 3),
                    rng.choice(INCIDENT_STATUSES),
                )
                if combo in seen_combos:
                    continue
                seen_combos.add(combo)
                category, severity, status = combo
                incident_rows.append(CentralIncidentSummary(
                    school=school, term_source_id=term_id, category=category,
                    severity=severity, status=status, count=rng.randint(1, 15),
                ))
            CentralIncidentSummary.objects.bulk_create(incident_rows, batch_size=200)
            made["incident_summaries"] += len(incident_rows)

            # billing summary: one row for the term
            issued = rng.randint(400_00, 2_200_00) * max(1, len(students) // 20)
            paid = int(issued * rng.uniform(0.55, 0.95))
            CentralBillingSummary.objects.update_or_create(
                school=school, term_source_id=term_id,
                defaults={
                    "issued_cents": issued, "paid_cents": paid,
                    "outstanding_cents": issued - paid,
                },
            )
            made["billing_summaries"] += 1

            # one FULL SnapshotBatch so the school doesn't show as
            # "never synced" on the dashboard/school-detail pages.
            SnapshotBatch.objects.create(
                school=school, kind=SnapshotBatch.Kind.FULL,
                manifest={
                    "school_id": str(school.pk), "snapshot_schema_version": 1,
                    "note": "synthetic demo batch, seed_demo command - no real bundle received",
                },
                content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                applied=True,
            )
            made["snapshot_batches"] += 1

        return made
