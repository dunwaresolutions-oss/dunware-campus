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
from apps.health.models import ActionPlan, Allergy, Condition, HealthProfile, Medication
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
                "action_plans": 0, "observations": 0, "applications": 0, "consents": 0}

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

        return made
