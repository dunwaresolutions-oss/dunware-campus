"""
Synthetic demo dataset — a primary school, grades 1 to 6, two classes per
grade, 25 pupils per class, on a 2026-2027 Bahamian school calendar. Every
record is invented; it NEVER contains a real child, family or staff member
(docs/PII_SECURITY.md §4). Refuses to run under production settings unless
--force is given.

    campus-app.exe manage seed_demo --force          # the full school
    campus-app.exe manage seed_demo --quick --force  # a tiny fast build
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
from apps.billing.gateways import ManualGateway
from apps.billing.models import FeeSchedule, Invoice, InvoiceLine, Payment
from apps.billing.services import issue_invoice
from apps.booking.models import AvailabilityWindow, Offering
from apps.booking.services import book, generate_slots
from apps.communication.models import Announcement, IncidentReport, MessageThread
from apps.communication.services import notify_incident, send_announcement
from apps.grades.models import (
    Assessment,
    AssessmentResult,
    AssessmentScheme,
    ReportCard,
    ReportCardEntry,
)
from apps.grades.services import generate_report_card, release_report_card
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
from apps.scheduling.models import AcademicYear, Closure, Room, SessionTemplate, Term
from apps.scheduling.services import generate_occurrences

# ── name pools (Bahamian-leaning, invented) ─────────────────────────────
FIRST = [
    "Aaliyah", "Amari", "Anaya", "Andre", "Ava", "Brianna", "Caleb", "Chloe",
    "Daniel", "David", "Deja", "Denzel", "Elijah", "Ella", "Ethan", "Gabriel",
    "Grace", "Imani", "Isaiah", "Jaden", "Jayla", "Jerome", "Josiah", "Kayla",
    "Keanu", "Keno", "Kian", "Layla", "Leah", "Liam", "Makayla", "Malik",
    "Maya", "Micah", "Nathan", "Nia", "Noah", "Olivia", "Omari", "Rhea",
    "Rico", "Sade", "Samuel", "Sasha", "Shania", "Tavares", "Theo", "Trey",
    "Zara", "Zion",
]
LAST = [
    "Adderley", "Bain", "Bethel", "Bowe", "Cartwright", "Cash", "Charlton",
    "Clarke", "Curry", "Darville", "Deveaux", "Dorsett", "Farrington", "Ferguson",
    "Forbes", "Gibson", "Hanna", "Higgs", "Johnson", "Knowles", "Lightbourne",
    "Major", "McKenzie", "Miller", "Moss", "Munroe", "Newbold", "Nixon",
    "Pinder", "Poitier", "Pratt", "Rahming", "Roberts", "Rolle", "Russell",
    "Sands", "Saunders", "Seymour", "Smith", "Stubbs", "Sweeting", "Symonette",
    "Taylor", "Thompson", "Turnquest", "Williams", "Wilson",
]
ALLERGENS = ["peanut", "tree nut", "dairy", "egg", "shellfish", "latex", "bee sting"]

SUBJECTS = [
    "English Language", "Mathematics", "Physical Education", "Religious Studies",
    "Social Studies", "Science", "Music", "Art",
]

# ── 2026-2027 calendar (from the operator's term sheet) ─────────────────
YEAR_NAME = "2026-2027"
YEAR_START = dt.date(2026, 8, 24)   # teachers re-open
YEAR_END = dt.date(2027, 6, 18)     # teachers close

TERM1 = (dt.date(2026, 8, 31), dt.date(2026, 12, 11))   # students open / close
TERM2 = (dt.date(2027, 1, 4), dt.date(2027, 6, 11))     # spans the old terms 2 & 3

# site-wide closures: public holidays observed + the mid-term / Easter breaks
SITE_CLOSURES = [
    # ── Term 1 ──
    (dt.date(2026, 10, 12), dt.date(2026, 10, 12), "National Heroes Day"),
    (dt.date(2026, 10, 23), dt.date(2026, 10, 23), "Mid-term break"),
    (dt.date(2026, 10, 26), dt.date(2026, 10, 26), "Mid-term break"),
    # ── Christmas break (between the terms) ──
    (dt.date(2026, 12, 25), dt.date(2026, 12, 25), "Christmas Day"),
    (dt.date(2026, 12, 26), dt.date(2026, 12, 26), "Boxing Day"),
    (dt.date(2027, 1, 1), dt.date(2027, 1, 1), "New Year's Day"),
    # ── Term 2 ──
    (dt.date(2027, 1, 11), dt.date(2027, 1, 11), "Majority Rule Day (observed)"),
    (dt.date(2027, 2, 19), dt.date(2027, 2, 19), "Mid-term break"),
    (dt.date(2027, 2, 22), dt.date(2027, 2, 22), "Mid-term break"),
    (dt.date(2027, 3, 22), dt.date(2027, 3, 29),
     "Easter break (incl. Good Friday & Easter Monday)"),
    (dt.date(2027, 5, 17), dt.date(2027, 5, 17), "Whit Monday"),
    (dt.date(2027, 6, 4), dt.date(2027, 6, 4), "Randol Fawkes Labour Day"),
]

DEMO_PASSWORD = "demo-Passphrase-123!"  # noqa: S105 - synthetic demo accounts only


class Command(BaseCommand):
    help = "Load a synthetic primary-school dataset (grades 1-6, 2 classes each)."

    def add_arguments(self, parser):
        parser.add_argument("--grades", type=int, default=6)
        parser.add_argument("--classes-per-grade", type=int, default=2)
        parser.add_argument("--class-size", type=int, default=25)
        parser.add_argument(
            "--quick", action="store_true",
            help="Tiny fast build for tests: 1 pupil/class, ~2 weeks of sessions.",
        )
        parser.add_argument(
            "--students", type=int, default=None,
            help="(compat) hard cap on the total number of pupils across all classes.",
        )
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete all existing operational data first (keeps superusers). "
                 "Use this to replace an earlier demo dataset cleanly.",
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
                self._flush()
            summary = self._seed(rng, options)
        for k, v in summary.items():
            self.stdout.write(f"{k:>24}: {v}")
        self.stdout.write(self.style.SUCCESS("demo data loaded"))

    # ------------------------------------------------------------------
    def _seed(self, rng, opts):
        quick = opts["quick"]
        grades = opts["grades"]
        cpg = 1 if quick else opts["classes_per_grade"]
        class_size = 1 if quick else opts["class_size"]
        cap_total = opts["students"]
        made = {}

        # ── staff ────────────────────────────────────────────────────
        head = self._user(rng, "headteacher", Role.ADMIN)
        front = self._user(rng, "frontdesk", Role.FRONT_DESK)
        n_classes = grades * cpg
        teachers = [self._user(rng, f"teacher{i + 1}", Role.TEACHER) for i in range(n_classes)]
        n_aides = 1 if quick else 4
        aides = [self._user(rng, f"aide{i + 1}", Role.TEACHER) for i in range(n_aides)]
        tutors = [self._user(rng, f"tutor{i + 1}", Role.TUTOR) for i in range(1 if quick else 2)]
        made["staff"] = 2 + len(teachers) + len(aides) + len(tutors)

        # ── the school year and its two terms ────────────────────────
        year = AcademicYear.objects.create(
            name=YEAR_NAME, start_date=YEAR_START, end_date=YEAR_END, is_current=True,
        )
        term1 = Term.objects.create(
            academic_year=year, name="Term 1 (Sep-Dec)", kind=Term.Kind.SEMESTER,
            start_date=TERM1[0], end_date=TERM1[1],
        )
        term2 = Term.objects.create(
            academic_year=year, name="Term 2 (Jan-Jun)", kind=Term.Kind.SEMESTER,
            start_date=TERM2[0], end_date=TERM2[1],
        )
        made["terms"] = 2

        # ── site-wide closures (holidays + breaks) ───────────────────
        for start, end, reason in SITE_CLOSURES:
            Closure.objects.create(start_date=start, end_date=end, reason=reason)
        made["closures"] = len(SITE_CLOSURES)

        # ── rooms ────────────────────────────────────────────────────
        specials = [
            Room.objects.create(name=n, kind=k, capacity=c)
            for n, k, c in [
                ("Gymnasium", Room.Kind.GYM, 120),
                ("Music Room", Room.Kind.RESOURCE, 30),
                ("Art Room", Room.Kind.RESOURCE, 30),
                ("Library", Room.Kind.RESOURCE, 40),
                ("Playing Field", Room.Kind.OUTDOOR, 200),
            ]
        ]

        # ── classes (Group per class) + their homeroom + pupils ──────
        classes = []            # list of (group, room, teacher)
        pupils_by_class = {}    # group.id -> [Student, ...]
        total_pupils = 0
        student_no = 1_000_001

        for g in range(1, grades + 1):
            for c in range(cpg):
                letter = chr(ord("A") + c)
                grp = Group.objects.create(
                    name=f"Grade {g}{letter}", kind=Group.Kind.CLASS,
                    stage_label=f"Grade {g}", capacity=opts["class_size"], active=True,
                )
                room = Room.objects.create(
                    name=f"Room {g}{letter}", kind=Room.Kind.CLASSROOM,
                    capacity=opts["class_size"],
                )
                lead = teachers[len(classes)]
                GroupStaff.objects.create(group=grp, user=lead, role=GroupStaff.Role.LEAD)
                if aides and not quick:
                    GroupStaff.objects.create(
                        group=grp, user=aides[len(classes) % len(aides)],
                        role=GroupStaff.Role.ASSISTANT,
                    )
                classes.append((grp, room, lead))

                pupils = []
                for _ in range(class_size):
                    if cap_total is not None and total_pupils >= cap_total:
                        break
                    p = self._make_pupil(rng, grp, term1, student_no, teachers)
                    student_no += 1
                    total_pupils += 1
                    pupils.append(p)
                pupils_by_class[grp.id] = pupils

        made["classes"] = len(classes)
        made["pupils"] = total_pupils
        made["guardians"] = Guardian.objects.count()

        # ── the timetable: one "school day" per class per weekday ────
        made["sessions"] = 0
        terms = [term1] if quick else [term1, term2]
        for term in terms:
            to_date = None
            if quick:
                to_date = min(term.start_date + dt.timedelta(days=13), term.end_date)
            for grp, room, lead in classes:
                for weekday in range(5):  # Mon-Fri
                    tmpl = SessionTemplate.objects.create(
                        group=grp, term=term, room=room, staff=lead, weekday=weekday,
                        start_time=dt.time(9, 0), end_time=dt.time(15, 0),
                        title=f"{grp.name} - school day",
                    )
                    made["sessions"] += generate_occurrences(tmpl, to_date=to_date)["created"]

        # ── attendance: check a couple of classes in for "today" ─────
        made["check_ins"] = 0
        for grp, _room, lead in classes[: (1 if quick else 2)]:
            for p in pupils_by_class[grp.id]:
                check_in(student=p, group=grp, by=lead, dropped_off_by_name="a guardian")
                made["check_ins"] += 1

        # ── lessons + grades, per class per subject ──────────────────
        made["curriculum_units"] = 0
        made["assessment_schemes"] = 0
        made["assessments"] = 0
        made["assessment_results"] = 0
        made["lesson_plans"] = 0
        for idx, (grp, _room, lead) in enumerate(classes):
            roster = pupils_by_class[grp.id]
            for s_i, subject in enumerate(SUBJECTS, start=1):
                unit = CurriculumUnit.objects.create(
                    group=grp, term=term1, title=f"{subject} - Unit 1",
                    summary=f"Synthetic {subject.lower()} unit for Grade {grp.stage_label}.",
                    sequence=s_i,
                )
                made["curriculum_units"] += 1
                LessonPlan.objects.create(
                    group=grp, unit=unit, author=lead, date=term1.start_date,
                    title=f"{subject}: introduction", objectives="Synthetic objectives.",
                    status=LessonPlan.Status.PUBLISHED,
                )
                made["lesson_plans"] += 1

                scheme = AssessmentScheme.objects.create(
                    group=grp, term=term1, name=subject, kind=AssessmentScheme.Kind.MIXED,
                )
                made["assessment_schemes"] += 1
                assessment = Assessment.objects.create(
                    scheme=scheme, group=grp, title=f"{subject} - Term 1 assessment",
                    date=term1.start_date + dt.timedelta(days=60),
                    max_mark=100, released=True, released_at=timezone.now(),
                )
                made["assessments"] += 1
                for p in roster:
                    AssessmentResult.objects.create(
                        assessment=assessment, student=p,
                        mark=rng.randint(48, 98), level=rng.randint(1, 4),
                        narrative="Synthetic feedback for demo purposes.",
                        graded_by=lead,
                    )
                    made["assessment_results"] += 1

            # ── report cards: one per pupil for Term 1 ──────────────
            first_class = idx == 0
            for p in roster:
                card = ReportCard.objects.create(
                    student=p, term=term1,
                    summary_narrative=(
                        f"{p.first_name} has settled well into Grade {grp.stage_label} "
                        "and is making steady progress across the curriculum."
                    ),
                )
                for o, subject in enumerate(SUBJECTS, start=1):
                    ReportCardEntry.objects.create(
                        report_card=card, subject=subject,
                        mark=rng.randint(50, 96), level=rng.randint(1, 4),
                        comment=f"Solid effort in {subject.lower()} this term.", order=o,
                    )
                if first_class:
                    generate_report_card(card)           # -> Finalized (+ a stored doc)
                    release_report_card(card)            # -> Released, visible on the portal
        made["report_cards"] = ReportCard.objects.count()

        # ── admissions pipeline for next year's Grade 1 ──────────────
        made["applications"] = 0
        g1 = classes[0][0] if classes else None
        for i in range(2 if quick else 9):
            afn, aln = rng.choice(FIRST), rng.choice(LAST)
            Application.objects.create(
                child_first_name=afn, child_last_name=aln,
                child_date_of_birth=dt.date(2021, 1, 1) + dt.timedelta(days=rng.randint(0, 300)),
                desired_start=dt.date(2027, 8, 30), desired_group=g1,
                applicant_name=f"{rng.choice(FIRST)} {aln}",
                applicant_email=f"apply{i}@example.test",
                applicant_phone=f"(242) 555-0{rng.randint(100, 999)}",
                status=rng.choice([
                    Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW,
                    Application.Status.WAITLISTED,
                ]),
            )
            made["applications"] += 1

        # ── booking: after-school offerings ─────────────────────────
        made["offerings"] = made["slots"] = made["bookings"] = 0
        all_pupils = list(Student.objects.all())
        offerings_spec = [("Homework Help", Offering.Kind.TUTORING, 6)] if quick else [
            ("Homework Help", Offering.Kind.TUTORING, 6),
            ("Football", Offering.Kind.SPORT, 20),
            ("Choir", Offering.Kind.MUSIC, 30),
            ("Reading Club", Offering.Kind.CLUB, 15),
        ]
        for title, kind, capacity in offerings_spec:
            off = Offering.objects.create(
                title=title, kind=kind, provider=rng.choice(tutors or teachers),
                room=rng.choice(specials), duration_minutes=60,
                capacity_per_slot=capacity, cancellation_hours=24, price_cents=None,
            )
            AvailabilityWindow.objects.create(
                offering=off, weekday=rng.randint(0, 4),
                start_time=dt.time(15, 15), end_time=dt.time(16, 15),
                valid_from=TERM1[0], valid_to=TERM1[0] + dt.timedelta(days=56),
            )
            made["slots"] += generate_slots(
                off, from_date=TERM1[0], to_date=TERM1[0] + dt.timedelta(days=56)
            )["created"]
            made["offerings"] += 1
            for slot in off.slots.all()[:3]:
                for p in rng.sample(all_pupils, k=min(len(all_pupils), capacity + 2)):
                    book(slot=slot, student=p, by=rng.choice(tutors or teachers))
                    made["bookings"] += 1

        # ── billing: fee schedules + an invoice per pupil ───────────
        tuition = FeeSchedule.objects.create(
            name="Term tuition", amount_cents=65_000, frequency=FeeSchedule.Frequency.TERM,
        )
        FeeSchedule.objects.create(
            name="Registration fee", amount_cents=10_000,
            frequency=FeeSchedule.Frequency.ONE_TIME,
        )
        FeeSchedule.objects.create(
            name="Activity fee", amount_cents=7_500, frequency=FeeSchedule.Frequency.TERM,
        )
        made["fee_schedules"] = 3
        made["invoices"] = made["payments"] = 0
        for p in all_pupils:
            inv = Invoice.objects.create(
                student=p, term=term1, due_date=TERM1[0] + dt.timedelta(days=30),
            )
            InvoiceLine.objects.create(
                invoice=inv, fee_schedule=tuition, description=tuition.name,
                unit_amount_cents=tuition.amount_cents,
            )
            issue_invoice(inv)
            made["invoices"] += 1
            if rng.random() < 0.7:
                ManualGateway().charge(
                    inv, inv.total_cents,
                    method=rng.choice([
                        Payment.Method.E_TRANSFER, Payment.Method.CASH, Payment.Method.CHEQUE,
                    ]),
                    received_by=front,
                )
                made["payments"] += 1

        # ── communication ──────────────────────────────────────────
        made["announcements"] = 0
        holiday_lines = "\n".join(
            f"  • {s:%d %b %Y}" + ("" if s == e else f" – {e:%d %b %Y}") + f": {r}"
            for s, e, r in SITE_CLOSURES
        )
        for title, body, audience in [
            ("Welcome to the 2026-2027 school year",
             "Classes begin Monday 31 August. Registration is 9:00-9:10 a.m. daily; "
             "pupils arriving after 9:10 a.m. are marked late. Dismissal is 3:00 p.m.",
             Announcement.Audience.WHOLE_SITE),
            ("Term dates & holidays 2026-2027",
             "Term 1: 31 Aug - 11 Dec 2026.  Term 2: 4 Jan - 11 Jun 2027.\n"
             "Closures:\n" + holiday_lines,
             Announcement.Audience.ALL_PARENTS),
            ("Monthly faculty meeting",
             "Faculty meets on the third Wednesday of each month at 2:00 p.m.; "
             "pupils are dismissed at 1:45 p.m. on those days.",
             Announcement.Audience.ALL_STAFF),
            ("PTA meeting - primary",
             "The primary-school PTA meets on the fourth Tuesday of each month at 6:30 p.m.",
             Announcement.Audience.ALL_PARENTS),
        ]:
            a = Announcement.objects.create(
                title=title, body=body, audience=audience, author=head,
                published_at=timezone.now(),
            )
            send_announcement(a)
            made["announcements"] += 1

        made["message_threads"] = 0
        subjects = (["About Friday pickup"] if quick else
                    ["About Friday pickup", "Field trip permission", "Homework question"])
        for subj in subjects:
            gl = (GuardianLink.objects
                  .filter(guardian__user__isnull=False, is_primary_contact=True)
                  .select_related("guardian__user", "student", "student__primary_group")
                  .first())
            if gl is None:
                break
            lead = GroupStaff.objects.filter(group=gl.student.primary_group).first()
            th = MessageThread.objects.create(
                subject=subj, student=gl.student, created_by=(lead.user if lead else head),
            )
            th.participants.add(lead.user if lead else head, gl.guardian.user)
            made["message_threads"] += 1

        made["incidents"] = 0
        if all_pupils:
            inc = IncidentReport.objects.create(
                student=rng.choice(all_pupils),
                occurred_at=timezone.now() - dt.timedelta(hours=3),
                category=IncidentReport.Category.INJURY,
                description="Synthetic playground scrape; cleaned and a plaster applied.",
                first_aid_given=True, reported_by=rng.choice(teachers),
            )
            notify_incident(inc)
            made["incidents"] = 1

        return made

    # ------------------------------------------------------------------
    def _flush(self):
        """Delete every operational row (keeps superusers and the audit log).
        Ordered leaf-first so PROTECT / non-cascading FKs don't block."""
        from apps.attendance.models import AttendanceRecord
        from apps.billing.models import Credit, Invoice, InvoiceLine, Payment
        from apps.booking.models import Booking, Slot
        from apps.communication.models import (
            IncidentAcknowledgement,
            Message,
            OutboundEmail,
        )
        from apps.grades.models import (
            Assessment,
            AssessmentResult,
            ReportCard,
            ReportCardEntry,
            RubricCriterion,
            RubricScore,
        )
        from apps.health.models import HealthAccessGrant
        from apps.lessons.models import CurriculumUnit, LessonPlan, LessonResource
        from apps.people.models import ContactChangeRequest, Document
        from apps.registration.models import (
            Application,
            ApplicationDocument,
            Consent,
            Enrolment,
            Offer,
            WaitlistEntry,
        )
        from apps.scheduling.models import (
            AcademicYear,
            Closure,
            Room,
            SessionOccurrence,
            SessionTemplate,
            Term,
        )

        ordered = [
            Payment, InvoiceLine, Credit, Invoice,
            RubricScore, AssessmentResult, Assessment, RubricCriterion,
            ReportCardEntry, ReportCard,
            Booking, Slot,  # AvailabilityWindow + Offering cascade from here / below
            LessonResource, LessonPlan, CurriculumUnit,
            Message, IncidentAcknowledgement, OutboundEmail,
            ContactChangeRequest,
            AttendanceRecord,
            Consent, Enrolment, Offer, WaitlistEntry, ApplicationDocument,
            SessionOccurrence, SessionTemplate, Closure,
            Document, HealthAccessGrant,
        ]
        for model in ordered:
            model.objects.all().delete()

        # things that cascade a lot when their parent goes
        from apps.billing.models import FeeSchedule
        from apps.booking.models import AvailabilityWindow, Offering
        from apps.communication.models import (
            Announcement,
            IncidentReport,
            MessageThread,
        )
        from apps.grades.models import AssessmentScheme
        from apps.people.models import (
            AuthorizedPickup,
            EmergencyContact,
            GroupStaff,
            GuardianLink,
            Observation,
        )

        for model in [AvailabilityWindow, Offering, FeeSchedule,
                      AssessmentScheme, Announcement, IncidentReport, MessageThread,
                      AuthorizedPickup, EmergencyContact, Observation, GuardianLink,
                      GroupStaff]:
            model.objects.all().delete()

        Application.objects.all().delete()   # SoftDelete: .objects still hard-deletes
        Term.objects.all().delete()
        AcademicYear.objects.all().delete()
        Room.objects.all().delete()
        Student.objects.all().delete()       # cascades remaining health rows
        Guardian.objects.all().delete()
        Group.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    # ------------------------------------------------------------------
    def _user(self, rng, username, role):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        u = User(username=username, email=f"{username}@example.test", role=role,
                 first_name=fn, last_name=ln)
        u.set_password(DEMO_PASSWORD)
        u.save()
        return u

    def _make_pupil(self, rng, grp, term1, number, teachers):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        grade_n = int(grp.stage_label.split()[-1])
        # a Grade-1 pupil is ~6, Grade-6 ~11
        age_years = 5 + grade_n + rng.choice([0, 0, 1])
        dob = dt.date(2026, 9, 1) - dt.timedelta(days=age_years * 365 + rng.randint(0, 300))
        p = Student.objects.create(
            first_name=fn, last_name=ln, date_of_birth=dob,
            student_number=f"S{number}", status=Student.Status.ENROLLED, primary_group=grp,
        )
        Enrolment.objects.create(student=p, group=grp, start_date=term1.start_date)

        # 1-2 guardians
        n_g = rng.choice([1, 2, 2])
        for j in range(n_g):
            gfn = rng.choice(FIRST)
            rel = (GuardianLink.Relationship.MOTHER if j == 0
                   else rng.choice([GuardianLink.Relationship.FATHER,
                                    GuardianLink.Relationship.GRANDPARENT]))
            g = Guardian.objects.create(
                first_name=gfn, last_name=ln,
                email=f"{gfn.lower()}.{ln.lower()}.{number}{j}@example.test",
                phone=f"(242) 555-{rng.randint(1000, 9999)}",
                address=f"{rng.randint(1, 199)} {rng.choice(FIRST)} Street, Nassau",
            )
            GuardianLink.objects.create(
                student=p, guardian=g, relationship=rel,
                is_primary_contact=(j == 0), has_custody=True, can_pickup=True,
                receives_communications=(j == 0), lives_with=(j == 0),
            )

        EmergencyContact.objects.create(
            student=p, name=f"{rng.choice(FIRST)} {ln}", relationship="aunt/uncle",
            phone=f"(242) 555-{rng.randint(1000, 9999)}", priority=1,
        )
        AuthorizedPickup.objects.create(
            student=p, name=f"{rng.choice(FIRST)} {ln}", relationship="grandparent",
            phone=f"(242) 555-{rng.randint(1000, 9999)}", active=True,
        )

        if rng.random() < 0.18:
            sev = rng.choice(list(Allergy.Severity.values))
            Allergy.objects.create(
                student=p, allergen=rng.choice(ALLERGENS), reaction="hives, swelling",
                severity=sev, epipen_required=(sev == Allergy.Severity.ANAPHYLAXIS),
            )
            if sev == Allergy.Severity.ANAPHYLAXIS:
                ActionPlan.objects.create(
                    student=p, kind=ActionPlan.Kind.ANAPHYLAXIS,
                    plan="Administer epinephrine, call 919, contact guardians.",
                    effective_from=term1.start_date,
                )
        if rng.random() < 0.10:
            Condition.objects.create(
                student=p, name="asthma", details="exercise-induced; inhaler on file",
            )
        if rng.random() < 0.08:
            Medication.objects.create(
                student=p, name="salbutamol", dose="2 puffs", schedule="PRN",
                route=Medication.Route.INHALED, prn=True,
            )
        HealthProfile.objects.get_or_create(student=p)

        for _ in range(rng.randint(0, 2)):
            Observation.objects.create(
                student=p, author=rng.choice(teachers),
                category=rng.choice(list(Observation.Category.values)),
                occurred_at=timezone.now() - dt.timedelta(days=rng.randint(1, 90)),
                body="Synthetic observation note for demo purposes.",
                visible_to_guardians=rng.random() < 0.5,
            )
        for kind in rng.sample(list(Consent.Kind.values), k=rng.randint(2, 5)):
            Consent.objects.create(
                student=p, kind=kind, granted=rng.random() < 0.85,
                granted_by_name=f"{p.first_name}'s guardian",
            )

        # give the first few families a portal login so the portal is testable
        if number <= 1_000_003:
            gl = p.guardian_links.filter(is_primary_contact=True).first()
            if gl and not gl.guardian.user_id:
                pu = User(username=f"parent{number - 1_000_000}",
                          email=gl.guardian.email, role=Role.PARENT,
                          first_name=gl.guardian.first_name, last_name=gl.guardian.last_name)
                pu.set_password(DEMO_PASSWORD)
                pu.save()
                gl.guardian.user = pu
                gl.guardian.save(update_fields=["user"])

        return p
