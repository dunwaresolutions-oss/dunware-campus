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
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import STAFF_ROLES, Role, User
from apps.attendance.models import AttendanceRecord
from apps.audit.models import AuditAction, AuditEntry
from apps.billing.gateways import ManualGateway
from apps.billing.models import Credit, FeeSchedule, Invoice, InvoiceLine, Payment
from apps.billing.services import issue_invoice, void_invoice
from apps.booking.models import AvailabilityWindow, Booking, Offering, Slot
from apps.booking.services import book, generate_slots
from apps.communication.models import (
    Announcement,
    IncidentAcknowledgement,
    IncidentReport,
    Message,
    MessageThread,
)
from apps.communication.services import notify_incident, send_announcement
from apps.grades.models import (
    Assessment,
    AssessmentResult,
    AssessmentScheme,
    ReportCard,
    ReportCardEntry,
    RubricCriterion,
    RubricScore,
)
from apps.grades.services import generate_report_card, release_report_card
from apps.health.models import (
    ActionPlan,
    Allergy,
    Condition,
    HealthAccessGrant,
    HealthProfile,
    Medication,
)
from apps.lessons.models import CurriculumUnit, LessonPlan, LessonResource
from apps.people.models import (
    AuthorizedPickup,
    ContactChangeRequest,
    Document,
    EmergencyContact,
    Group,
    GroupStaff,
    Guardian,
    GuardianLink,
    Observation,
    Student,
)
from apps.registration.models import Application, Consent, Enrolment, WaitlistEntry
from apps.registration.services import make_offer, respond_to_offer
from apps.scheduling.models import (
    AcademicYear,
    Closure,
    Room,
    SessionOccurrence,
    SessionTemplate,
    Term,
)
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
        all_pupils = [p for lst in pupils_by_class.values() for p in lst]

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

        # ── attendance: a real history for every class ───────────────
        today = timezone.localdate()
        window_start = max(term1.start_date, today - dt.timedelta(days=35))
        closed_days: set[dt.date] = set()
        for cl in Closure.objects.filter(group__isnull=True):
            d = cl.start_date
            while d <= cl.end_date:
                closed_days.add(d)
                d += dt.timedelta(days=1)
        school_days: list[dt.date] = []
        d = window_start
        while d <= today:
            if d.weekday() < 5 and d not in closed_days:
                school_days.append(d)
            d += dt.timedelta(days=1)

        S = AttendanceRecord.Status
        chronic_ids = set(
            rng.sample([p.id for p in all_pupils], k=min(8, len(all_pupils)))
        ) if all_pupils else set()
        classes_for_att = classes if not quick else classes[:1]
        att_rows: list[AttendanceRecord] = []
        made["check_ins"] = 0
        for grp, _room, lead in classes_for_att:
            for p in pupils_by_class[grp.id]:
                for day in school_days:
                    r = rng.random()
                    if day == today and r < 0.05:
                        att_rows.append(
                            AttendanceRecord(student=p, group=grp, date=day, status=S.EXPECTED)
                        )
                        continue
                    if p.id in chronic_ids:
                        status = (
                            S.ABSENT if r < 0.45 else S.LATE if r < 0.62 else S.PRESENT
                        )
                    elif r < 0.90:
                        status = S.PRESENT
                    elif r < 0.94:
                        status = S.LATE
                    elif r < 0.965:
                        status = S.ABSENT
                    elif r < 0.985:
                        status = S.EXCUSED
                    else:
                        status = S.LEFT_EARLY
                    rec = AttendanceRecord(student=p, group=grp, date=day, status=status)
                    if status in (S.PRESENT, S.LATE, S.LEFT_EARLY):
                        cin = timezone.make_aware(
                            dt.datetime.combine(
                                day, dt.time(9, 5 if status == S.LATE else 0)
                            )
                        )
                        rec.checked_in_at = cin
                        rec.checked_in_by = lead
                        rec.dropped_off_by_name = "a guardian"
                        if day < today or r < 0.5:
                            rec.checked_out_at = cin.replace(
                                hour=(13 if status == S.LEFT_EARLY else 15), minute=0
                            )
                            rec.checked_out_by = lead
                            rec.collected_by_name = "a guardian"
                        if day == today:
                            made["check_ins"] += 1
                    att_rows.append(rec)
        AttendanceRecord.objects.bulk_create(att_rows, batch_size=500)
        made["attendance_records"] = len(att_rows)

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
        _app_cycle = [
            Application.Status.SUBMITTED,
            Application.Status.UNDER_REVIEW,
            Application.Status.WAITLISTED,
        ]
        for i in range(6 if quick else 9):
            afn, aln = rng.choice(FIRST), rng.choice(LAST)
            Application.objects.create(
                child_first_name=afn, child_last_name=aln,
                child_date_of_birth=dt.date(2021, 1, 1) + dt.timedelta(days=rng.randint(0, 300)),
                desired_start=dt.date(2027, 8, 30), desired_group=g1,
                applicant_name=f"{rng.choice(FIRST)} {aln}",
                applicant_email=f"apply{i}@example.test",
                applicant_phone=f"(242) 555-0{rng.randint(100, 999)}",
                status=_app_cycle[i % 3],
            )
            made["applications"] += 1

        # ── booking: after-school offerings ─────────────────────────
        made["offerings"] = made["slots"] = made["bookings"] = 0
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

        # ══════════════════════════════════════════════════════════════
        # Fill every remaining console section — no table left empty.
        # ══════════════════════════════════════════════════════════════
        staff_all = [head, front, *teachers, *aides, *tutors]
        portal_links = list(
            GuardianLink.objects.filter(guardian__user__isnull=False).select_related(
                "guardian__user", "student"
            )
        )

        # ── a past academic year (history) ──────────────────────────
        prev_year = AcademicYear.objects.create(
            name="2025-2026", start_date=dt.date(2025, 8, 25),
            end_date=dt.date(2026, 6, 19), is_current=False,
        )
        Term.objects.create(
            academic_year=prev_year, name="Full year (2025-26)",
            kind=Term.Kind.YEAR_ROUND,
            start_date=prev_year.start_date, end_date=prev_year.end_date,
        )

        # ── group-staff: one inactive assignment ────────────────────
        if len(classes) > 1 and aides:
            GroupStaff.objects.create(
                group=classes[1][0], user=aides[0],
                role=GroupStaff.Role.ASSISTANT, active=False,
            )

        # ── TOTP devices so MFA-coverage isn't 0% ───────────────────
        for u in staff_all:
            if u is head or u is front or rng.random() < 0.7:
                TOTPDevice.objects.get_or_create(
                    user=u, name="default", defaults={"confirmed": True}
                )

        # ── student portal logins for a few Grade 6 pupils ──────────
        made["student_logins"] = 0
        senior = [c for c in classes if c[0].stage_label == "Grade 6"]
        for grp, _r, _l in senior[:1]:
            for p in pupils_by_class[grp.id][:3]:
                su = User(
                    username=f"student{p.student_number}", email="",
                    role=Role.STUDENT, first_name=p.first_name, last_name=p.last_name,
                )
                su.set_password(DEMO_PASSWORD)
                su.save()
                p.user = su
                p.save(update_fields=["user"])
                made["student_logins"] += 1

        # ── synthetic recent auth events for the security panel ─────
        ips = ["203.0.113.7", "198.51.100.22", "203.0.113.41"]
        for act, n, summ in [
            (AuditAction.LOGIN, 6, "signed in"),
            (AuditAction.LOGIN_FAILED, 4, "bad password"),
            (AuditAction.LOCKOUT, 1, "locked out after 5 attempts"),
            (AuditAction.MFA_VERIFIED, 5, "second factor accepted"),
            (AuditAction.PERMISSION_DENIED, 3, "denied /api/billing/"),
            (AuditAction.LOGOUT, 3, "signed out"),
        ]:
            for _ in range(1 if quick else n):
                who = rng.choice(staff_all)
                AuditEntry.objects.create(
                    action=act, actor=who,
                    actor_label=who.get_full_name() or who.username,
                    actor_role=who.role, source_ip=rng.choice(ips), summary=summ,
                )

        # ── backup history (feeds the Backups section + metrics) ───
        from apps.reporting.models import BackupRun

        base_dt = timezone.now()
        for d in range(7, 0, -1):
            day = base_dt - dt.timedelta(days=d, hours=rng.randint(0, 2))
            ok = d != 3  # one failed run mid-week
            BackupRun.objects.create(
                kind=BackupRun.Kind.SCHEDULED,
                status=BackupRun.Status.SUCCESS if ok else BackupRun.Status.FAILED,
                started_at=day,
                finished_at=day + dt.timedelta(seconds=rng.randint(20, 90)),
                archive_name=f"campus-{day:%Y%m%d-%H%M%S}.zip.gpg" if ok else "",
                size_bytes=rng.randint(38_000_000, 46_000_000) if ok else None,
                database_ok=ok, media_ok=ok, encrypted=True,
                archives_retained=(d + 6) if ok else None,
                error="" if ok else "pg_dump exited with code 1",
                host="CAMPUS-SERVER", build="demo",
            )
        BackupRun.objects.create(
            kind=BackupRun.Kind.VERIFY, status=BackupRun.Status.SUCCESS,
            started_at=base_dt - dt.timedelta(days=6, hours=1),
            finished_at=base_dt - dt.timedelta(days=6),
            archive_name="campus-verify.zip.gpg", database_ok=True, media_ok=True,
            host="CAMPUS-SPARE", build="demo",
        )

        # ── rubric criteria + scores on every scheme ────────────────
        made["rubric_criteria"] = made["rubric_scores"] = 0
        crit_labels = ["Understanding", "Application", "Communication", "Effort"]
        score_rows: list[RubricScore] = []
        schemes = list(AssessmentScheme.objects.all())
        for scheme in schemes[: (1 if quick else len(schemes))]:
            crits = [
                RubricCriterion.objects.create(
                    scheme=scheme, label=lbl, order=o + 1, max_level=4,
                    descriptor=f"Demo descriptor for {lbl.lower()}.",
                )
                for o, lbl in enumerate(crit_labels[: (2 if quick else 4)])
            ]
            made["rubric_criteria"] += len(crits)
            for res in AssessmentResult.objects.filter(assessment__scheme=scheme):
                for cr in crits:
                    score_rows.append(
                        RubricScore(result=res, criterion=cr, level=rng.randint(1, 4))
                    )
        RubricScore.objects.bulk_create(score_rows, batch_size=1000)
        made["rubric_scores"] = len(score_rows)

        # ── lesson resources + draft plans + a term-2 unit ─────────
        made["lesson_resources"] = 0
        for lp in LessonPlan.objects.all()[: (1 if quick else 40)]:
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.LINK,
                title="Reference slides", url="https://example.test/slides",
            )
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.NOTE, title="Teacher note",
                body="Bring the number cards from the store cupboard.",
            )
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.FILE, title="Worksheet",
                file=ContentFile(b"Demo worksheet content.\n", name="worksheet.txt"),
            )
            made["lesson_resources"] += 3
        for grp, _r, lead in classes[: (1 if quick else 3)]:
            u2 = CurriculumUnit.objects.create(
                group=grp, term=term2, title="Term 2 - Unit 1",
                summary="Synthetic term-2 unit.", sequence=1,
            )
            LessonPlan.objects.create(
                group=grp, unit=u2, author=lead, date=term2.start_date,
                title="Term 2 opener (draft)", objectives="Draft objectives.",
                status=LessonPlan.Status.DRAFT,
            )

        # ── report cards: finalise (not release) a second class ─────
        for card in ReportCard.objects.filter(status=ReportCard.Status.DRAFT)[
            : (1 if quick else 25)
        ]:
            generate_report_card(card)
        made["report_cards"] = ReportCard.objects.count()

        # ── registration: waitlist rows + offers in every state ─────
        made["offers"] = made["waitlist"] = 0
        for app in Application.objects.filter(status=Application.Status.WAITLISTED):
            WaitlistEntry.objects.get_or_create(
                application=app,
                defaults={"group": g1, "priority": rng.choice([10, 50, 100])},
            )
            made["waitlist"] += 1
        review_apps = list(
            Application.objects.filter(status=Application.Status.UNDER_REVIEW)
        )
        expires = timezone.now() + dt.timedelta(days=14)
        for i, app in enumerate(review_apps[: (1 if quick else 6)]):
            off = make_offer(
                app, group=g1, start_date=dt.date(2027, 8, 30),
                expires_at=expires, actor=front,
            )
            made["offers"] += 1
            if i % 3 == 1:
                respond_to_offer(off, accept=True, actor=front)
            elif i % 3 == 2:
                respond_to_offer(off, accept=False, actor=front)
        for st in (Application.Status.DECLINED, Application.Status.WITHDRAWN):
            Application.objects.create(
                child_first_name=rng.choice(FIRST), child_last_name=rng.choice(LAST),
                child_date_of_birth=dt.date(2021, 5, 1), applicant_name="A Parent",
                applicant_email=f"{st.lower()}@example.test", status=st, desired_group=g1,
            )

        # ── messages in every thread ───────────────────────────────
        made["messages"] = 0
        for th in MessageThread.objects.all():
            staff_p = th.participants.filter(role__in=STAFF_ROLES).first()
            parent_p = th.participants.exclude(role__in=STAFF_ROLES).first()
            turns = [
                (parent_p, "Good afternoon - could you confirm the arrangement?"),
                (staff_p, "Yes, that's fine. Thank you for letting us know."),
                (parent_p, "Wonderful, thank you."),
            ]
            for sender, body in turns[: (1 if quick else 3)]:
                Message.objects.create(thread=th, sender=sender, body=body)
                made["messages"] += 1
            th.last_message_at = timezone.now()
            th.save(update_fields=["last_message_at"])
        first_thread = MessageThread.objects.first()
        if first_thread:
            first_thread.closed = True
            first_thread.save(update_fields=["closed"])

        # ── incidents: one per category, varied severity + status ──
        made["incident_acks"] = 0
        cat_list = list(IncidentReport.Category.values)
        for j, cat in enumerate(cat_list[: (3 if quick else len(cat_list))]):
            stu = rng.choice(all_pupils)
            inc = IncidentReport.objects.create(
                student=stu,
                occurred_at=timezone.now() - dt.timedelta(days=rng.randint(1, 20)),
                category=cat, severity=rng.randint(1, 5),
                location=rng.choice(["playground", "classroom", "gym", "hallway"]),
                description=f"Synthetic {cat.lower()} incident for demo purposes.",
                action_taken="Guardians informed; monitored.",
                first_aid_given=rng.random() < 0.4, reported_by=rng.choice(teachers),
            )
            if j == 0:
                continue  # leave as DRAFT
            notify_incident(inc)  # -> SENT
            if j % 2 == 0:
                for gl in stu.guardian_links.filter(receives_communications=True):
                    IncidentAcknowledgement.objects.create(
                        incident=inc, guardian=gl.guardian,
                        acknowledged_by=gl.guardian.user, signature_name=str(gl.guardian),
                    )
                    made["incident_acks"] += 1
                inc.status = IncidentReport.Status.ACKNOWLEDGED
                inc.save(update_fields=["status"])
        made["incidents"] = IncidentReport.objects.count()

        # ── announcement: one unpublished draft ────────────────────
        Announcement.objects.create(
            title="Sports day - date to be confirmed",
            body="We are finalising a date for the annual sports day. Details to follow.",
            audience=Announcement.Audience.ALL_PARENTS, author=head,
        )

        # ── billing: draft / partial / void / overdue + credits ────
        made["credits"] = 0
        reg_fee = FeeSchedule.objects.get(name="Registration fee")
        for k, p in enumerate(all_pupils[: (2 if quick else 24)]):
            inv = Invoice.objects.create(
                student=p, term=term1,
                due_date=(today - dt.timedelta(days=10)) if k % 4 == 3
                else (today + dt.timedelta(days=20)),
            )
            InvoiceLine.objects.create(
                invoice=inv, fee_schedule=reg_fee, description=reg_fee.name,
                unit_amount_cents=reg_fee.amount_cents,
            )
            mode = k % 4
            if mode == 1:
                issue_invoice(inv)
            elif mode == 2:
                issue_invoice(inv)
                ManualGateway().charge(
                    inv, inv.total_cents // 2, method=Payment.Method.CASH,
                    received_by=front,
                )
            elif mode == 3:
                issue_invoice(inv)
                inv.status = Invoice.Status.OVERDUE
                inv.save(update_fields=["status", "updated_at"])
            # mode 0 stays DRAFT
        for p in all_pupils[: (1 if quick else 6)]:
            Credit.objects.create(
                student=p, amount_cents=rng.choice([2500, 5000, 7500]),
                reason="Goodwill adjustment (demo).", created_by=front,
            )
            made["credits"] += 1
        v = Invoice.objects.filter(status=Invoice.Status.ISSUED).first()
        if v:
            void_invoice(v, reason="Issued in error (demo).", actor=front)
        made["invoices"] = Invoice.objects.count()
        made["payments"] = Payment.objects.count()

        # ── booking: exercise every status + a cancelled slot ──────
        for b in list(Booking.objects.all())[: (1 if quick else 12)]:
            b.status = rng.choice([
                Booking.Status.ATTENDED, Booking.Status.NO_SHOW, Booking.Status.CANCELLED,
            ])
            if b.status == Booking.Status.CANCELLED:
                b.cancelled_at = timezone.now()
                b.cancelled_by = front
                b.waitlist_position = None
            b.save()
        far_slot = (
            Slot.objects.filter(status=Slot.Status.OPEN).order_by("-starts_at").first()
        )
        if far_slot:
            far_slot.status = Slot.Status.CANCELLED
            far_slot.save(update_fields=["status"])

        # ── portal: contact-change requests in each state ─────────
        made["change_requests"] = 0
        for i, gl in enumerate(portal_links[: (1 if quick else 5)]):
            field, cur, prop = rng.choice([
                ("phone", "(242) 555-0000", "(242) 555-9999"),
                ("address", "1 Old Street, Nassau", "42 New Street, Nassau"),
                ("email", gl.guardian.email, f"updated.{gl.guardian.email}"),
            ])
            ccr = ContactChangeRequest.objects.create(
                requested_by=gl.guardian.user, guardian=gl.guardian, field=field,
                current_value=cur, proposed_value=prop,
                reason="We have moved / changed number.",
            )
            if i % 3 == 1:
                ccr.status = ContactChangeRequest.Status.APPROVED
                ccr.reviewed_by, ccr.reviewed_at = front, timezone.now()
                ccr.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            elif i % 3 == 2:
                ccr.status = ContactChangeRequest.Status.REJECTED
                ccr.reviewed_by, ccr.reviewed_at = front, timezone.now()
                ccr.review_note = "Please bring photo ID to the office."
                ccr.save(update_fields=[
                    "status", "reviewed_by", "reviewed_at", "review_note",
                ])
            made["change_requests"] += 1

        # ── student & application documents ───────────────────────
        made["documents"] = 0
        for p in all_pupils[: (2 if quick else 40)]:
            Document.objects.create(
                student=p, kind=rng.choice(list(Document.Kind.values)),
                title="Scanned record (demo)", uploaded_by=front,
                file=ContentFile(b"%PDF-1.4 demo document\n", name="record.pdf"),
            )
            made["documents"] += 1
        from apps.registration.models import ApplicationDocument
        for app in Application.objects.all()[: (1 if quick else 4)]:
            ApplicationDocument.objects.create(
                application=app, title="Birth certificate (demo)", uploaded_by=front,
                file=ContentFile(b"%PDF-1.4 demo\n", name="bc.pdf"),
            )

        # ── health-access grants for aides / tutors ───────────────
        for u in (aides + tutors)[: (1 if quick else 4)]:
            HealthAccessGrant.objects.get_or_create(
                user=u,
                defaults={"granted_by": head, "reason": "Classroom support (demo)."},
            )

        # ── cancel a handful of sessions ─────────────────────────
        for occ in SessionOccurrence.objects.filter(
            status=SessionOccurrence.Status.SCHEDULED
        ).order_by("?")[: (1 if quick else 6)]:
            occ.status = SessionOccurrence.Status.CANCELLED
            occ.cancelled_reason = "Teacher absent (demo)."
            occ.save(update_fields=["status", "cancelled_reason"])

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
        from apps.reporting.models import BackupRun
        from apps.scheduling.models import (
            AcademicYear,
            Closure,
            Room,
            SessionOccurrence,
            SessionTemplate,
            Term,
        )

        ordered = [
            BackupRun,
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

        # deterministically cover every health table + action-plan kind
        # on the first handful of pupils; the rest are probabilistic.
        forced = number - 1_000_000
        if forced == 1 or rng.random() < 0.14:
            Allergy.objects.create(
                student=p, allergen=rng.choice(ALLERGENS), reaction="hives, swelling",
                severity=Allergy.Severity.ANAPHYLAXIS, epipen_required=True,
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.ANAPHYLAXIS,
                plan="Administer epinephrine, call 919, contact guardians.",
                effective_from=term1.start_date, review_by=term1.end_date,
            )
        elif rng.random() < 0.10:
            sev = rng.choice([Allergy.Severity.MILD, Allergy.Severity.MODERATE,
                              Allergy.Severity.SEVERE])
            Allergy.objects.create(
                student=p, allergen=rng.choice(ALLERGENS), reaction="rash",
                severity=sev, epipen_required=False,
            )
        if forced == 2 or rng.random() < 0.10:
            Condition.objects.create(
                student=p, name="asthma", details="exercise-induced; inhaler on file",
                diagnosed_on=dt.date(2024, 3, 1), ongoing=True,
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.ASTHMA,
                plan="Reliever inhaler; rest; call guardians if no improvement.",
                effective_from=term1.start_date,
            )
        if forced == 3 or rng.random() < 0.08:
            Medication.objects.create(
                student=p, name="salbutamol", dose="2 puffs", schedule="PRN",
                route=Medication.Route.INHALED, prn=True, prescriber="Dr Demo",
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.SEIZURE,
                plan="Time the seizure; recovery position; call 919 if over 5 min.",
                effective_from=term1.start_date,
            )
        if forced == 4:
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.DIABETES,
                plan="Check blood glucose; follow the sliding-scale sheet.",
                effective_from=term1.start_date,
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.OTHER, plan="General care note.",
                effective_from=term1.start_date,
            )
        HealthProfile.objects.get_or_create(
            student=p, defaults={"blood_type": rng.choice(["O+", "A+", "B+", "AB+"])}
        )

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
