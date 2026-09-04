"""
Synthetic demo dataset — a small daycare + a secondary school, entirely made
up. NEVER contains a real child, family, or staff record (docs/PII_SECURITY.md
§4). Refuses to run under production settings unless --force is given.
"""
from __future__ import annotations

import datetime as dt
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.attendance.services import check_in
from apps.booking.models import AvailabilityWindow, Offering
from apps.booking.services import book, generate_slots
from apps.health.models import ActionPlan, Allergy, Condition, HealthProfile, Medication
from apps.lessons.models import CurriculumUnit, LessonPlan
from apps.people.models import (
    AuthorizedPickup,
    EmergencyContact,
    Group,
    GroupStaff,
    Guardian,
    GuardianLink,
    Observation,
    Student,
)
from apps.registration.models import Application, Consent, Enrolment
from apps.scheduling.models import AcademicYear, Room, SessionTemplate, Term
from apps.scheduling.services import generate_occurrences

FIRST = ["Ada", "Bo", "Cai", "Dev", "Esi", "Finn", "Gia", "Hana", "Ira", "Jae",
         "Kit", "Lux", "Mira", "Noa", "Oki", "Pax", "Quin", "Rai", "Sol", "Tao",
         "Uma", "Vic", "Wren", "Xan", "Yuki", "Zev"]
LAST = ["Ash", "Brook", "Chen", "Diaz", "Eze", "Fox", "Gill", "Haddad", "Ito",
         "Jonas", "Kaur", "Lund", "Mensah", "Novak", "Oso",
         "Park", "Quirke", "Roy", "Singh", "Tran", "Ugo", "Voss", "Walsh"]
ALLERGENS = ["peanut", "tree nut", "dairy", "egg", "shellfish", "latex", "bee sting"]


def _name(rng):
    return rng.choice(FIRST), rng.choice(LAST)


class Command(BaseCommand):
    help = "Load a small synthetic demo dataset (daycare + secondary school)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=24)
        parser.add_argument("--seed", type=int, default=1729)
        parser.add_argument("--force", action="store_true",
                            help="Allow running even when DEBUG is False")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed with DEBUG=False. Pass --force if you mean it.")

        # deterministic synthetic demo data — not a security context
        rng = random.Random(options["seed"])  # nosec B311
        with transaction.atomic():
            summary = self._seed(rng, options["students"])
        for k, v in summary.items():
            self.stdout.write(f"{k:>22}: {v}")
        self.stdout.write(self.style.SUCCESS("demo data loaded"))

    def _seed(self, rng, n_students):
        rooms = [
            Group.objects.create(name=n, kind=Group.Kind.ROOM, stage_label=s)
            for n, s in [("Sunflower Room", "Infant"), ("Maple Room", "Toddler"),
                         ("Cedar Room", "Preschool")]
        ]
        sections = [
            Group.objects.create(name=n, kind=Group.Kind.SECTION, stage_label=s)
            for n, s in [("SNC2D-01", "Grade 10 Science"), ("ENG3U-02", "Grade 11 English"),
                         ("MPM1D-03", "Grade 9 Math")]
        ]
        groups = rooms + sections

        teachers = []
        for i in range(4):
            fn, ln = _name(rng)
            u = User(username=f"teacher{i}", email=f"teacher{i}@example.test",
                     role=Role.TEACHER, first_name=fn, last_name=ln)
            u.set_password("demo-Passphrase-123!")
            u.save()
            teachers.append(u)
        for grp in groups:
            GroupStaff.objects.create(group=grp, user=rng.choice(teachers),
                                      role=GroupStaff.Role.LEAD)

        today = timezone.localdate()
        made = {"groups": len(groups), "teachers": len(teachers), "students": 0,
                "guardians": 0, "allergies": 0, "conditions": 0, "medications": 0,
                "action_plans": 0, "observations": 0, "applications": 0, "consents": 0,
                "sessions": 0, "check_ins": 0, "lesson_plans": 0}

        # ── scheduling: a year + term, rooms, a weekly template per group ──
        year = AcademicYear.objects.create(
            name=f"{today.year}-{today.year + 1}",
            start_date=today - dt.timedelta(days=30),
            end_date=today + dt.timedelta(days=120), is_current=True,
        )
        term = Term.objects.create(
            academic_year=year, name="Term 1", kind=Term.Kind.SEMESTER,
            start_date=today - dt.timedelta(days=30), end_date=today + dt.timedelta(days=60),
        )
        campus_rooms = [
            Room.objects.create(name=n, kind=k)
            for n, k in [("Room A", Room.Kind.CLASSROOM), ("Room B", Room.Kind.CLASSROOM),
                         ("Gym", Room.Kind.GYM), ("Yard", Room.Kind.OUTDOOR)]
        ]
        for grp in groups:
            tmpl = SessionTemplate.objects.create(
                group=grp, term=term, room=rng.choice(campus_rooms),
                staff=rng.choice(teachers), weekday=rng.randint(0, 4),
                start_time=dt.time(9, 0), end_time=dt.time(10, 0), title="Morning session",
            )
            made["sessions"] += generate_occurrences(tmpl)["created"]

        for i in range(n_students):
            fn, ln = _name(rng)
            is_daycare = i < n_students // 2
            grp = rng.choice(rooms if is_daycare else sections)
            age_days = rng.randint(365, 5 * 365) if is_daycare else rng.randint(13 * 365, 18 * 365)
            student = Student.objects.create(
                first_name=fn, last_name=ln,
                date_of_birth=today - dt.timedelta(days=age_days),
                student_number=f"S{1_000_000 + i}",
                status=Student.Status.ENROLLED,
                primary_group=grp,
            )
            Enrolment.objects.create(student=student, group=grp,
                                     start_date=today - dt.timedelta(days=rng.randint(30, 400)))
            made["students"] += 1

            # 1–2 guardians
            for j in range(rng.randint(1, 2)):
                gfn, _gl = _name(rng)
                guardian = Guardian.objects.create(
                    first_name=gfn, last_name=ln,
                    email=f"{gfn.lower()}.{ln.lower()}{i}{j}@example.test",
                    phone=f"555-01{rng.randint(10, 99)}",
                    address=f"{rng.randint(10, 999)} Example Ave, Testville",
                )
                GuardianLink.objects.create(
                    student=student, guardian=guardian,
                    relationship=rng.choice(list(GuardianLink.Relationship.values)),
                    is_primary_contact=(j == 0),
                )
                made["guardians"] += 1

            EmergencyContact.objects.create(
                student=student, name=f"{_name(rng)[0]} {ln}", relationship="aunt/uncle",
                phone=f"555-02{rng.randint(10, 99)}", priority=1,
            )
            AuthorizedPickup.objects.create(
                student=student, name=f"{_name(rng)[0]} {ln}", relationship="grandparent",
                phone=f"555-03{rng.randint(10, 99)}",
            )

            if rng.random() < 0.35:
                sev = rng.choice(list(Allergy.Severity.values))
                Allergy.objects.create(
                    student=student, allergen=rng.choice(ALLERGENS), reaction="hives, swelling",
                    severity=sev, epipen_required=(sev == Allergy.Severity.ANAPHYLAXIS),
                )
                made["allergies"] += 1
                if sev == Allergy.Severity.ANAPHYLAXIS:
                    ActionPlan.objects.create(
                        student=student, kind=ActionPlan.Kind.ANAPHYLAXIS,
                        plan="Administer epinephrine, call 911, contact guardians.",
                        effective_from=today,
                    )
                    made["action_plans"] += 1
            if rng.random() < 0.2:
                Condition.objects.create(student=student, name="asthma",
                                         details="exercise-induced; inhaler on file")
                made["conditions"] += 1
            if rng.random() < 0.15:
                Medication.objects.create(student=student, name="salbutamol",
                                          dose="2 puffs", schedule="PRN", prn=True)
                made["medications"] += 1

            HealthProfile.objects.get_or_create(student=student)

            for _ in range(rng.randint(0, 3)):
                Observation.objects.create(
                    student=student, author=rng.choice(teachers),
                    category=rng.choice(list(Observation.Category.values)),
                    occurred_at=timezone.now() - dt.timedelta(days=rng.randint(1, 120)),
                    body="Synthetic observation note for demo purposes.",
                    visible_to_guardians=rng.random() < 0.5,
                )
                made["observations"] += 1

            for kind in rng.sample(list(Consent.Kind.values), k=rng.randint(1, 4)):
                Consent.objects.create(
                    student=student, kind=kind, granted=rng.random() < 0.85,
                    granted_by_name=f"{fn}'s guardian",
                )
                made["consents"] += 1

        # a handful of pipeline applications
        for i in range(6):
            afn, aln = _name(rng)
            Application.objects.create(
                child_first_name=afn, child_last_name=aln,
                child_date_of_birth=today - dt.timedelta(days=rng.randint(365, 2000)),
                desired_start=today + dt.timedelta(days=rng.randint(10, 120)),
                desired_group=rng.choice(rooms),
                applicant_name=f"{_name(rng)[0]} {aln}",
                applicant_email=f"apply{i}@example.test",
                applicant_phone=f"555-09{rng.randint(10, 99)}",
                status=rng.choice([Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW,
                                   Application.Status.WAITLISTED]),
            )
            made["applications"] += 1

        # ── attendance: check a slice of today's roster in ──
        for enr in Enrolment.objects.filter(status=Enrolment.Status.ACTIVE)[:12]:
            check_in(student=enr.student, group=enr.group,
                     by=rng.choice(teachers), dropped_off_by_name="a guardian")
            made["check_ins"] += 1

        # ── lessons: a unit + a couple of plans per group ──
        for grp in groups:
            unit = CurriculumUnit.objects.create(
                group=grp, term=term, title="Unit 1", summary="Synthetic unit.", sequence=1
            )
            for d in range(2):
                LessonPlan.objects.create(
                    group=grp, unit=unit, author=rng.choice(teachers),
                    date=today + dt.timedelta(days=d * 2),
                    title=f"Lesson {d + 1}", objectives="Synthetic objectives.",
                    status=LessonPlan.Status.PUBLISHED if d == 0 else LessonPlan.Status.DRAFT,
                )
                made["lesson_plans"] += 1

        # ── booking: two offerings, a weekly window each, some bookings ──
        made["offerings"] = 0
        made["slots"] = made.get("slots", 0)
        made["bookings"] = 0
        students = list(Student.objects.all())
        for title, kind, cap in [("Maths tutoring", Offering.Kind.TUTORING, 1),
                                 ("Chess club", Offering.Kind.CLUB, 6)]:
            off = Offering.objects.create(
                title=title, kind=kind, provider=rng.choice(teachers),
                room=rng.choice(campus_rooms), duration_minutes=45,
                capacity_per_slot=cap, cancellation_hours=24, price_cents=None,
            )
            AvailabilityWindow.objects.create(
                offering=off, weekday=rng.randint(0, 4),
                start_time=dt.time(15, 30), end_time=dt.time(17, 0),
                valid_from=today, valid_to=today + dt.timedelta(days=42),
            )
            made["slots"] += generate_slots(
                off, from_date=today, to_date=today + dt.timedelta(days=42)
            )["created"]
            made["offerings"] += 1
            for slot in off.slots.all()[:4]:
                for student in rng.sample(students, k=min(len(students), cap + 1)):
                    book(slot=slot, student=student, by=rng.choice(teachers))
                    made["bookings"] += 1

        return made
