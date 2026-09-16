"""
Synthetic demo dataset — a high school, grades 7 to 12, on a 2026-2027
Bahamian school calendar. Every record is invented; it NEVER contains a real
student, family or staff member (docs/PII_SECURITY.md §4). Refuses to run
under production settings unless --force is given.

Models a real secondary-school shape, not just a bigger primary school:

- Every grade has several homerooms (Group.Kind.CLASS) sized ~30, used for
  daily attendance and for the subjects every student in that grade takes
  together.
- Every student takes six **compulsory subjects** the whole way through
  (Mathematics, English Language, Physical Education, Religious Studies,
  Civics, Biology) plus, in grades 7-9, a shared "junior" set (French,
  Information Technology, Art, Music) everyone in the grade takes together —
  delivered at the homeroom, no streaming yet.
- From grade 10, students **stream into a course of study** — one of five
  named tracks, each three subjects layered on top of the compulsory set
  (e.g. Academic Science: Physics/Chemistry/Computer Science; Business:
  Typing/Accounts/Record Keeping) — plus a shared Career Guidance period.
  Track subjects are taught in cross-homeroom sections (Group.Kind.SECTION),
  the way a real timetable streams students by subject choice, not homeroom.
  A student's track has no dedicated database field (none exists in the
  model — this seeds real data, it doesn't grow the schema); it's fully
  recoverable from which sections a student is enrolled in, and is also
  spelled out in one of that student's Observations for readability.

    campus-app.exe manage seed_demo --force              # the full school (1400)
    campus-app.exe manage seed_demo --force --students 400   # a smaller school
    campus-app.exe manage seed_demo --quick --force       # a tiny fast build
"""
from __future__ import annotations

import datetime as dt
import itertools
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
from apps.communication.services import notify_early_dismissal, notify_incident, send_announcement
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
    EarlyDismissal,
    Room,
    SessionOccurrence,
    SessionTemplate,
    Term,
)
from apps.scheduling.services import generate_occurrences
from apps.staffchat.models import StaffChatCursor, StaffMessage

# ── name pools (Bahamian-leaning, invented) ─────────────────────────────
FIRST = [
    "Aaliyah", "Amari", "Anaya", "Andre", "Ava", "Brianna", "Caleb", "Chloe",
    "Daniel", "David", "Deja", "Denzel", "Elijah", "Ella", "Ethan", "Gabriel",
    "Grace", "Imani", "Isaiah", "Jaden", "Jayla", "Jerome", "Josiah", "Kayla",
    "Keanu", "Keno", "Kian", "Layla", "Leah", "Liam", "Makayla", "Malik",
    "Maya", "Micah", "Nathan", "Nia", "Noah", "Olivia", "Omari", "Rhea",
    "Rico", "Sade", "Samuel", "Sasha", "Shania", "Tavares", "Theo", "Trey",
    "Zara", "Zion", "Alanna", "Byron", "Cadence", "Dario", "Emory", "Fabian",
    "Gianna", "Hosea", "Ivy", "Jaylen", "Kiara", "Lorenzo", "Marcus", "Nadia",
    "Orlando", "Prisha", "Quincy", "Renata", "Silas", "Talia", "Uriah",
    "Vanessa", "Wesley", "Xiomara", "Yolanda", "Zavier",
]
# Guardians are adults, drawn from their own pools (never FIRST, the pupil
# pool) so a guardian can never end up sharing a full name with an unrelated
# student - and so MOTHER/FATHER always get a first name that actually
# matches, rather than the pre-fix behaviour of picking from FIRST with no
# regard for the relationship being assigned (found 2026-09-16: a guardian
# named "Hosea" - and coincidentally sharing a full name with an actual
# pupil - recorded as a "Mother").
FEMALE_FIRST = [
    "Patrice", "Shantelle", "Andrea", "Monique", "Verona", "Delores",
    "Althea", "Carmen", "Yvette", "Patricia", "Sharon", "Cheryl", "Donna",
    "Ingrid", "Marva", "Sonia", "Beverly", "Charmaine", "Denise", "Portia",
    "Simone", "Lavern", "Cassandra", "Petra",
]
MALE_FIRST = [
    "Anthony", "Kendal", "Wellington", "Godfrey", "Cyril", "Rupert",
    "Vernon", "Leroy", "Winston", "Clement", "Percy", "Aldrick", "Basil",
    "Edison", "Franklyn", "Garnet", "Herman", "Ivor", "Julian", "Kelvin",
    "Lennox", "Maxwell", "Neville", "Osric",
]
LAST = [
    "Adderley", "Bain", "Bethel", "Bowe", "Cartwright", "Cash", "Charlton",
    "Clarke", "Curry", "Darville", "Deveaux", "Dorsett", "Farrington", "Ferguson",
    "Forbes", "Gibson", "Hanna", "Higgs", "Johnson", "Knowles", "Lightbourne",
    "Major", "McKenzie", "Miller", "Moss", "Munroe", "Newbold", "Nixon",
    "Pinder", "Poitier", "Pratt", "Rahming", "Roberts", "Rolle", "Russell",
    "Sands", "Saunders", "Seymour", "Smith", "Stubbs", "Sweeting", "Symonette",
    "Taylor", "Thompson", "Turnquest", "Williams", "Wilson", "Albury",
    "Butler", "Collie", "Delancy", "Edgecombe", "Fawkes", "Gray", "Hepburn",
    "Ingraham", "Josey", "Kemp", "Lundy", "Mackey", "Neely", "Oliver",
    "Percentie", "Quant", "Ritchie", "Strachan", "Thurston", "Vanderpool",
]
ALLERGENS = ["peanut", "tree nut", "dairy", "egg", "shellfish", "latex", "bee sting"]

# ── the curriculum: compulsory-for-everyone, junior-shared, and the five
#    senior "courses of study" (tracks) students stream into from Grade 10 ──
COMPULSORY_SUBJECTS = [
    "Mathematics", "English Language", "Physical Education",
    "Religious Studies", "Civics", "Biology",
]
JUNIOR_SHARED_SUBJECTS = ["French", "Information Technology", "Art", "Music"]
CAREER_GUIDANCE = "Career Guidance"

TRACKS: dict[str, list[str]] = {
    "Academic Science": ["Physics", "Chemistry", "Computer Science"],
    "Business": ["Typing", "Accounts", "Record Keeping"],
    "General Arts": ["History", "Geography", "Literature"],
    "Technical & Vocational": ["Technical Drawing", "Woodworking", "Electrical Installation"],
    "Home Economics": ["Food & Nutrition", "Clothing & Textiles", "Child Development"],
}
# relative popularity, not a hard quota — students stream in individually.
TRACK_WEIGHTS = {
    "Academic Science": 20, "Business": 25, "General Arts": 25,
    "Technical & Vocational": 15, "Home Economics": 15,
}
# a dedicated room for each track subject; compulsory/junior-shared subjects
# are taught in the student's own homeroom, like a real junior-high timetable.
SPECIAL_ROOMS = {
    "Physics": "Physics Lab", "Chemistry": "Chemistry Lab",
    "Computer Science": "Computer Lab",
    "Typing": "Business Lab", "Accounts": "Business Lab",
    "Record Keeping": "Business Lab",
    "History": "Humanities Room", "Geography": "Humanities Room",
    "Literature": "Humanities Room",
    "Technical Drawing": "Technical Drawing Room", "Woodworking": "Woodwork Shop",
    "Electrical Installation": "Electrical Workshop",
    "Food & Nutrition": "Home Economics Room", "Clothing & Textiles": "Home Economics Room",
    "Child Development": "Home Economics Room",
}
ALL_TRACK_SUBJECTS = [s for subs in TRACKS.values() for s in subs]

# a homeroom's own daily period grid (compulsory/junior-shared subjects);
# course-of-study sections get their own separate single weekly slot instead.
PERIODS_PER_DAY = [
    (dt.time(8, 0), dt.time(8, 50)),
    (dt.time(9, 0), dt.time(9, 50)),
    (dt.time(10, 0), dt.time(10, 50)),
    (dt.time(11, 0), dt.time(11, 50)),
    (dt.time(12, 30), dt.time(13, 20)),
    (dt.time(13, 30), dt.time(14, 20)),
]

GRADES = [7, 8, 9, 10, 11, 12]
# relative grade sizes (some natural senior attrition) — rescaled to whatever
# --students total is asked for, always summing exactly to it.
GRADE_WEIGHTS = {7: 250, 8: 245, 9: 240, 10: 230, 11: 220, 12: 215}  # = 1400

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

# a tiny, well-known transparent 1x1 PNG — enough for an ImageField that
# nothing actually renders pixel-for-pixel in this dataset.
_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ── small generic helpers ────────────────────────────────────────────────
def _allocate(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder apportionment: `total` split across `weights`
    (any positive numbers), returned as ints that sum exactly to `total`."""
    s = sum(weights) or 1
    if total <= 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    remainder = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[:max(remainder, 0)]:
        base[i] += 1
    return base


def _split_counts(total: int, parts: int) -> list[int]:
    """`total` split as evenly as possible across `parts` positive buckets."""
    if total <= 0:
        return []
    parts = max(1, min(parts, total))
    q, r = divmod(total, parts)
    return [q + 1 if i < r else q for i in range(parts)]


def _unique_username(first: str, last: str, taken: set) -> str:
    base = "".join(ch for ch in f"{first[0]}{last}".lower() if ch.isalnum()) or "user"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}{n}"
        n += 1
    taken.add(candidate)
    return candidate


class Command(BaseCommand):
    help = "Load a synthetic high-school dataset (grades 7-12, streamed courses of study)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students", type=int, default=1400,
            help="Target total enrolled students, apportioned across grades 7-12.",
        )
        parser.add_argument(
            "--quick", action="store_true",
            help="Tiny fast build for tests: ~12 pupils total, ~2 weeks of sessions.",
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
    def _seed(self, rng, opts):  # noqa: C901, PLR0915 - one deliberate, linear seed script
        quick = opts["quick"]
        total_students = 12 if quick else max(6, opts["students"])
        max_class_size = 4 if quick else 30
        max_section_size = 4 if quick else 32
        made = {}
        taken_usernames: set[str] = set()

        # ── per-grade student targets, always summing to total_students ──
        grade_counts = dict(zip(
            GRADES, _allocate(total_students, [GRADE_WEIGHTS[g] for g in GRADES]), strict=True
        ))

        # ── staff (created before the school profile, which points at one) ──
        head = self._user(rng, taken_usernames, Role.ADMIN)
        front = self._user(rng, taken_usernames, Role.FRONT_DESK)

        # one dedicated subject teacher per distinct subject in the whole
        # curriculum — 26 specialists, the way a real high school staffs it.
        all_subjects = (
            COMPULSORY_SUBJECTS + JUNIOR_SHARED_SUBJECTS + ALL_TRACK_SUBJECTS + [CAREER_GUIDANCE]
        )
        subject_teacher = {
            subj: self._user(rng, taken_usernames, Role.TEACHER) for subj in all_subjects
        }
        # a form (homeroom) teacher for every homeroom we're about to build.
        n_homerooms = sum(
            len(_split_counts(grade_counts[g], max(1, -(-grade_counts[g] // max_class_size))))
            for g in GRADES
        )
        form_teachers = [
            self._user(rng, taken_usernames, Role.TEACHER) for _ in range(n_homerooms)
        ]
        n_aides = 1 if quick else 6
        aides = [self._user(rng, taken_usernames, Role.TEACHER) for _ in range(n_aides)]
        tutors = [self._user(rng, taken_usernames, Role.TUTOR) for _ in range(1 if quick else 3)]
        all_teachers = list({*subject_teacher.values(), *form_teachers})
        staff_all = [head, front, *all_teachers, *aides, *tutors]
        made["staff"] = len(staff_all)

        # ── the school's own identity (report-card letterhead) ───────
        from apps.core.models import SchoolProfile, SiteConfiguration

        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            country="BS", currency="BSD", locale="en-BS", collects_fees=True,
        )
        made["site_config"] = 1

        SchoolProfile.objects.all().delete()
        SchoolProfile.objects.create(
            name="Windward Cay High School",
            legal_name="Windward Cay High School (Ministry of Education, District 4)",
            motto="Knowledge · Discipline · Service",
            address_line1="27 Explorer Boulevard",
            address_line2="Windward Cay Settlement",
            city="Nassau", region="New Providence", postal_code="N-4471", country="Bahamas",
            phone="(242) 555-0198", email="office@windwardcay.example",
            website="windwardcay.example",
            principal_name=f"{head.first_name} {head.last_name}", principal_title="Principal",
            principal_user=head,
            signature=ContentFile(_PIXEL_PNG, name="principal-signature.png"),
            logo=ContentFile(_PIXEL_PNG, name="logo.png"),
            report_card_footer=(
                "This report is confidential and intended for the parent or "
                "guardian named above.\nWindward Cay High School — Ministry of Education"
            ),
        )
        made["school_profile"] = 1

        # ── grading policy: activate the Bahamas 4.0 GPA preset (seeded by
        #    a migration, present on every install) — matches this school's
        #    own identity and exercises the cumulative-GPA calculation on
        #    every report card generated below.
        from apps.grades.models import GradingScheme

        bahamas_gpa = GradingScheme.objects.filter(name="Bahamas — 4.0 GPA").first()
        if bahamas_gpa:
            bahamas_gpa.activate()
        made["grading_scheme"] = bahamas_gpa.name if bahamas_gpa else "none"

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

        # ── rooms: shared specials + one lab/workshop per track subject ──
        specials = [
            Room.objects.create(name=n, kind=k, capacity=c)
            for n, k, c in [
                ("Gymnasium", Room.Kind.GYM, 200),
                ("Auditorium", Room.Kind.RESOURCE, 400),
                ("Music Room", Room.Kind.RESOURCE, 40),
                ("Art Room", Room.Kind.RESOURCE, 35),
                ("Library", Room.Kind.RESOURCE, 60),
                ("Playing Field", Room.Kind.OUTDOOR, 300),
            ]
        ]
        special_rooms = {
            label: Room.objects.create(
                name=label, kind=Room.Kind.RESOURCE, capacity=max_section_size
            )
            for label in sorted(set(SPECIAL_ROOMS.values()))
        }

        # ══════════════════════════════════════════════════════════════
        # Homerooms + students, grade by grade.
        # ══════════════════════════════════════════════════════════════
        homerooms_by_grade: dict[int, list[tuple]] = {}   # grade -> [(group, room, lead), ...]
        pupils_by_class: dict = {}                        # group.id -> [Student, ...]
        student_track: dict = {}                          # student.id -> track name (senior only)
        student_subjects: dict = {}                        # student.id -> [(subject, group), ...]
        all_pupils: list[Student] = []
        student_no = 7_000_001
        form_teacher_iter = iter(form_teachers)

        for g in GRADES:
            grade_total = grade_counts[g]
            n_classes = max(1, -(-grade_total // max_class_size))  # ceil division
            class_sizes = _split_counts(grade_total, n_classes)
            homerooms_by_grade[g] = []
            for c, size in enumerate(class_sizes):
                letter = chr(ord("A") + c)
                grp = Group.objects.create(
                    name=f"Grade {g}{letter}", kind=Group.Kind.CLASS,
                    stage_label=f"Grade {g}", capacity=max_class_size, active=True,
                )
                room = Room.objects.create(
                    name=f"Room {g}{letter}", kind=Room.Kind.CLASSROOM, capacity=max_class_size,
                )
                lead = next(form_teacher_iter)
                GroupStaff.objects.create(group=grp, user=lead, role=GroupStaff.Role.LEAD)
                if aides and rng.random() < 0.5:
                    GroupStaff.objects.create(
                        group=grp, user=rng.choice(aides), role=GroupStaff.Role.ASSISTANT,
                    )
                homerooms_by_grade[g].append((grp, room, lead))

                roster = []
                for _ in range(size):
                    p = self._make_pupil(
                        rng, grp, g, term1, student_no, all_teachers, taken_usernames
                    )
                    student_no += 1
                    roster.append(p)
                    student_subjects[p.id] = []
                pupils_by_class[grp.id] = roster
                all_pupils.extend(roster)

                # compulsory + (junior-shared | career guidance) — delivered
                # to the whole homeroom, exactly like a real junior-high day.
                homeroom_subjects = COMPULSORY_SUBJECTS + (
                    JUNIOR_SHARED_SUBJECTS if g <= 9 else [CAREER_GUIDANCE]
                )
                for subj in homeroom_subjects:
                    for p in roster:
                        student_subjects[p.id].append((subj, grp))

        made["classes"] = sum(len(v) for v in homerooms_by_grade.values())
        made["pupils"] = len(all_pupils)

        # ══════════════════════════════════════════════════════════════
        # Streaming: from Grade 10, every student picks a course of study.
        # ══════════════════════════════════════════════════════════════
        track_names = list(TRACKS)
        track_weights = [TRACK_WEIGHTS[t] for t in track_names]
        section_groups: list[tuple] = []   # (group, subject, roster, teacher, subj_idx)
        for g in (10, 11, 12):
            roster_by_track: dict[str, list[Student]] = {t: [] for t in track_names}
            for grp, _room, _lead in homerooms_by_grade[g]:
                for p in pupils_by_class[grp.id]:
                    track = rng.choices(track_names, weights=track_weights, k=1)[0]
                    student_track[p.id] = track
                    roster_by_track[track].append(p)

            for track, students in roster_by_track.items():
                if not students:
                    continue
                n_chunks = max(1, -(-len(students) // max_section_size))
                chunk_sizes = _split_counts(len(students), n_chunks)
                offset = 0
                for chunk_i, size in enumerate(chunk_sizes, start=1):
                    chunk = students[offset:offset + size]
                    offset += size
                    for subj_idx, subj in enumerate(TRACKS[track]):
                        sec = Group.objects.create(
                            name=f"{subj} — Grade {g} {track} Sec {chunk_i}",
                            kind=Group.Kind.SECTION, stage_label=f"Grade {g}",
                            capacity=max_section_size, active=True,
                        )
                        teacher = subject_teacher[subj]
                        GroupStaff.objects.create(
                            group=sec, user=teacher, role=GroupStaff.Role.LEAD
                        )
                        for p in chunk:
                            Enrolment.objects.create(
                                student=p, group=sec, start_date=term1.start_date
                            )
                            student_subjects[p.id].append((subj, sec))
                        # subj_idx (0/1/2, a subject's fixed position within
                        # its track) drives which of the 3 reserved weekdays
                        # this section meets on - see the timetable pass
                        # below, which guarantees this never collides with
                        # this student's homeroom-delivered periods, or with
                        # her *other* two track subjects either.
                        section_groups.append((sec, subj, chunk, teacher, subj_idx))
                # one readable record of the student's course of study, since
                # no dedicated field for it exists on Student.
                for p in students:
                    Observation.objects.create(
                        student=p, author=head, category=Observation.Category.ACADEMIC,
                        occurred_at=timezone.now() - dt.timedelta(days=rng.randint(1, 10)),
                        body=(
                            f"Streamed into the {track} course of study for senior school "
                            f"({', '.join(TRACKS[track])}), on top of the compulsory subjects."
                        ),
                        visible_to_guardians=True,
                    )
        made["course_of_study_sections"] = len(section_groups)

        # ── the timetable: a real period-by-period breakdown, not one
        #    all-day "school day" blob — every homeroom subject gets its own
        #    weekly slot(s), cycling through the grade's subject list to fill
        #    the week, so the calendar shows what a student is actually in.
        #
        #    A senior student (grade 10-12) is in two worlds at once: her
        #    homeroom (compulsory subjects) AND her course-of-study sections
        #    (track subjects) - both scheduling the SAME physical student, so
        #    a naive independent assignment can and did double-book her (the
        #    same period used by both a homeroom subject and a track
        #    subject). Fixed by reserving the *last* daily period exclusively
        #    for track sections in grades 10-12 - homeroom-delivered subjects
        #    there never touch it - so no senior student can ever be double-
        #    booked, regardless of which track she's in. Grades 7-9 have no
        #    tracks at all, so they use every period freely. ──
        made["sessions"] = 0
        terms = [term1] if quick else [term1, term2]
        homerooms_flat = [hr for lst in homerooms_by_grade.values() for hr in lst]
        periods = PERIODS_PER_DAY[:2] if quick else PERIODS_PER_DAY
        n_periods = len(periods)
        track_period_idx = n_periods - 1  # reserved for course-of-study sections
        homeroom_period_range = range(n_periods) if n_periods < 2 else range(n_periods - 1)
        for term in terms:
            to_date = None
            if quick:
                to_date = min(term.start_date + dt.timedelta(days=13), term.end_date)
            for g in GRADES:
                homeroom_subjects = COMPULSORY_SUBJECTS + (
                    JUNIOR_SHARED_SUBJECTS if g <= 9 else [CAREER_GUIDANCE]
                )
                # senior grades keep the last period free of homeroom subjects
                periods_here = list(homeroom_period_range) if g >= 10 else list(range(n_periods))
                slots_here = [(wd, p) for wd in range(5) for p in periods_here]
                subject_cycle = list(
                    itertools.islice(itertools.cycle(homeroom_subjects), len(slots_here))
                )
                for grp, room, lead in homerooms_by_grade[g]:
                    for (weekday, p_idx), subj in zip(slots_here, subject_cycle, strict=True):
                        start, end = periods[p_idx]
                        teacher = subject_teacher.get(subj, lead)
                        tmpl = SessionTemplate.objects.create(
                            group=grp, term=term, room=room, staff=teacher, weekday=weekday,
                            start_time=start, end_time=end, title=subj,
                        )
                        made["sessions"] += generate_occurrences(tmpl, to_date=to_date)["created"]
        # course-of-study sections: every term, always in the reserved last
        # period, on a weekday fixed by the subject's position (0/1/2) within
        # its own track - so any one student's three track subjects always
        # land on three different weekdays, never on top of each other, and
        # never on top of any of her homeroom periods either. The demo fixes
        # those three weekdays by subject position purely for reproducible
        # demo data - a real deployment would let the school say which days
        # its own course-of-study periods fall on, not have this hardcoded.
        #
        # That leaves the *other* two weekdays of this same reserved period
        # (Tue/Thu) unused by any track subject - rather than a silent gap,
        # every senior homeroom gets an explicit, supervised "Free Period"
        # there, so a student's day is always fully accounted for.
        track_start, track_end = periods[track_period_idx if n_periods > 1 else 0]
        track_weekdays = [0, 2, 4]  # Mon / Wed / Fri - always 3 apart or more
        free_period_weekdays = [1, 3]  # Tue / Thu - the reserved period's off days
        for term in terms:
            to_date = None
            if quick:
                to_date = min(term.start_date + dt.timedelta(days=13), term.end_date)
            for sec, subj, _chunk, teacher, subj_idx in section_groups:
                weekday = track_weekdays[subj_idx % len(track_weekdays)]
                room = special_rooms.get(SPECIAL_ROOMS.get(subj))
                tmpl = SessionTemplate.objects.create(
                    group=sec, term=term, room=room, staff=teacher, weekday=weekday,
                    start_time=track_start, end_time=track_end,
                    title=f"{subj} period",
                )
                made["sessions"] += generate_occurrences(tmpl, to_date=to_date)["created"]
            for g in (10, 11, 12):
                for grp, room, lead in homerooms_by_grade[g]:
                    for weekday in free_period_weekdays:
                        tmpl = SessionTemplate.objects.create(
                            group=grp, term=term, room=room, staff=lead, weekday=weekday,
                            start_time=track_start, end_time=track_end,
                            title="Free Period",
                        )
                        made["sessions"] += generate_occurrences(tmpl, to_date=to_date)["created"]

        # ── attendance: a real history for every homeroom ─────────────
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
            rng.sample([p.id for p in all_pupils], k=min(40, len(all_pupils)))
        ) if all_pupils else set()
        homerooms_for_att = homerooms_flat if not quick else homerooms_flat[:1]
        att_rows: list[AttendanceRecord] = []
        made["check_ins"] = 0
        for grp, _room, lead in homerooms_for_att:
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
                                day, dt.time(8, 5 if status == S.LATE else 0)
                            )
                        )
                        rec.checked_in_at = cin
                        rec.checked_in_by = lead
                        rec.dropped_off_by_name = "a guardian"
                        if day < today or r < 0.5:
                            rec.checked_out_at = cin.replace(
                                hour=(12 if status == S.LEFT_EARLY else 14), minute=30
                            )
                            rec.checked_out_by = lead
                            rec.collected_by_name = "a guardian"
                        if day == today:
                            made["check_ins"] += 1
                    att_rows.append(rec)
        AttendanceRecord.objects.bulk_create(att_rows, batch_size=1000)
        made["attendance_records"] = len(att_rows)

        # ══════════════════════════════════════════════════════════════
        # Lessons + grades: one unified pass over every (group, subject)
        # delivery unit — a homeroom teaching a compulsory/shared subject,
        # or a cross-homeroom section teaching a track subject.
        # ══════════════════════════════════════════════════════════════
        delivery_units = []
        for g in GRADES:
            for grp, _room, lead in homerooms_by_grade[g]:
                subjects = COMPULSORY_SUBJECTS + (
                    JUNIOR_SHARED_SUBJECTS if g <= 9 else [CAREER_GUIDANCE]
                )
                for subj in subjects:
                    teacher = subject_teacher.get(subj, lead)
                    delivery_units.append((grp, subj, pupils_by_class[grp.id], teacher))
        for sec, subj, chunk, teacher, _subj_idx in section_groups:
            delivery_units.append((sec, subj, chunk, teacher))

        made["curriculum_units"] = made["assessment_schemes"] = 0
        made["assessments"] = made["lesson_plans"] = 0
        result_rows: list[AssessmentResult] = []
        for s_i, (grp, subj, roster, teacher) in enumerate(delivery_units, start=1):
            unit = CurriculumUnit.objects.create(
                group=grp, term=term1, title=f"{subj} - Unit 1",
                summary=f"Synthetic {subj.lower()} unit for {grp.name}.",
                sequence=1,
            )
            made["curriculum_units"] += 1
            LessonPlan.objects.create(
                group=grp, unit=unit, author=teacher, date=term1.start_date,
                title=f"{subj}: introduction", objectives="Synthetic objectives.",
                status=LessonPlan.Status.PUBLISHED,
            )
            made["lesson_plans"] += 1

            scheme = AssessmentScheme.objects.create(
                group=grp, term=term1, name=subj, kind=AssessmentScheme.Kind.MIXED,
            )
            made["assessment_schemes"] += 1
            assessment = Assessment.objects.create(
                scheme=scheme, group=grp, title=f"{subj} - Term 1 assessment",
                date=term1.start_date + dt.timedelta(days=60),
                max_mark=100, released=(s_i % 3 != 0), released_at=(
                    timezone.now() if s_i % 3 != 0 else None
                ),
            )
            made["assessments"] += 1
            for p in roster:
                result_rows.append(AssessmentResult(
                    assessment=assessment, student=p,
                    mark=rng.randint(48, 98), level=rng.randint(1, 4),
                    narrative="Synthetic feedback for demo purposes.",
                    graded_by=teacher,
                ))
        AssessmentResult.objects.bulk_create(result_rows, batch_size=2000)
        made["assessment_results"] = len(result_rows)

        # ── report cards: one per pupil for Term 1, entries mirroring
        #    exactly the subjects that student's own delivery units cover ──
        report_cards = []
        for p in all_pupils:
            report_cards.append(ReportCard(
                student=p, term=term1,
                summary_narrative=(
                    f"{p.first_name} has settled well into "
                    f"{p.primary_group.name if p.primary_group else 'the new grade'} "
                    "and is making steady progress across the curriculum."
                ),
            ))
        ReportCard.objects.bulk_create(report_cards, batch_size=1000)
        cards_by_student = {c.student_id: c for c in report_cards}

        entry_rows: list[ReportCardEntry] = []
        for p in all_pupils:
            card = cards_by_student[p.id]
            for o, (subj, grp) in enumerate(student_subjects.get(p.id, []), start=1):
                entry_rows.append(ReportCardEntry(
                    report_card=card, subject=subj, group=grp,
                    mark=rng.randint(50, 96), level=rng.randint(1, 4),
                    comment=f"Solid effort in {subj.lower()} this term.", order=o,
                ))
        ReportCardEntry.objects.bulk_create(entry_rows, batch_size=2000)
        made["report_card_entries"] = len(entry_rows)

        first_homeroom_ids = {p.id for p in pupils_by_class[homerooms_flat[0][0].id]}
        for card in report_cards:
            if card.student_id in first_homeroom_ids:
                generate_report_card(card)     # -> Finalized (+ a stored doc)
                release_report_card(card)      # -> Released, visible on the portal
        made["report_cards"] = ReportCard.objects.count()

        # ══════════════════════════════════════════════════════════════
        # Fill every remaining console section — no table left empty.
        # ══════════════════════════════════════════════════════════════

        # ── admissions pipeline for next year's incoming Grade 7 ─────
        made["applications"] = 0
        entry_homeroom = homerooms_by_grade[7][0][0]
        _app_cycle = [
            Application.Status.SUBMITTED,
            Application.Status.UNDER_REVIEW,
            Application.Status.WAITLISTED,
        ]
        for i in range(6 if quick else 15):
            afn, aln = rng.choice(FIRST), rng.choice(LAST)
            Application.objects.create(
                child_first_name=afn, child_last_name=aln,
                child_date_of_birth=dt.date(2014, 1, 1) + dt.timedelta(days=rng.randint(0, 300)),
                desired_start=dt.date(2027, 8, 30), desired_group=entry_homeroom,
                applicant_name=f"{rng.choice(FIRST)} {aln}",
                applicant_email=f"apply{i}@example.test",
                applicant_phone=f"(242) 555-0{rng.randint(100, 999)}",
                status=_app_cycle[i % 3],
            )
            made["applications"] += 1

        # ── booking: after-school offerings, high-school flavoured ────
        made["offerings"] = made["slots"] = made["bookings"] = 0
        offerings_spec = [("Homework Help", Offering.Kind.TUTORING, 10)] if quick else [
            ("Homework Help", Offering.Kind.TUTORING, 15),
            ("Track & Field", Offering.Kind.SPORT, 40),
            ("Choir", Offering.Kind.MUSIC, 35),
            ("Debate Club", Offering.Kind.CLUB, 20),
            ("Robotics Club", Offering.Kind.CLUB, 18),
        ]
        for title, kind, capacity in offerings_spec:
            off = Offering.objects.create(
                title=title, kind=kind, provider=rng.choice(tutors or all_teachers),
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
                    book(slot=slot, student=p, by=rng.choice(tutors or all_teachers))
                    made["bookings"] += 1

        # ── billing: fee schedules + an invoice per pupil ───────────
        tuition = FeeSchedule.objects.create(
            name="Term tuition", amount_cents=95_000, frequency=FeeSchedule.Frequency.TERM,
        )
        FeeSchedule.objects.create(
            name="Registration fee", amount_cents=15_000,
            frequency=FeeSchedule.Frequency.ONE_TIME,
        )
        FeeSchedule.objects.create(
            name="Activity fee", amount_cents=12_000, frequency=FeeSchedule.Frequency.TERM,
        )
        FeeSchedule.objects.create(
            name="Science lab fee", amount_cents=8_500, frequency=FeeSchedule.Frequency.TERM,
        )
        made["fee_schedules"] = 4
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
             "Classes begin Monday 31 August. Homeroom registration is 8:00-8:10 a.m. daily; "
             "students arriving after 8:10 a.m. are marked late. Dismissal is 2:30 p.m.",
             Announcement.Audience.WHOLE_SITE),
            ("Term dates & holidays 2026-2027",
             "Term 1: 31 Aug - 11 Dec 2026.  Term 2: 4 Jan - 11 Jun 2027.\n"
             "Closures:\n" + holiday_lines,
             Announcement.Audience.ALL_PARENTS),
            ("Grade 10 course-of-study streaming",
             "Grade 10 students have been streamed into their course of study (Academic "
             "Science, Business, General Arts, Technical & Vocational, or Home Economics). "
             "Timetables reflecting the new sections are posted in homeroom.",
             Announcement.Audience.WHOLE_SITE),
            ("Monthly faculty meeting",
             "Faculty meets on the third Wednesday of each month at 2:45 p.m.; "
             "students are dismissed at 2:15 p.m. on those days.",
             Announcement.Audience.ALL_STAFF),
            ("PTA meeting",
             "The PTA meets on the fourth Tuesday of each month at 6:30 p.m. in the auditorium.",
             Announcement.Audience.ALL_PARENTS),
        ]:
            a = Announcement.objects.create(
                title=title, body=body, audience=audience, author=head,
                published_at=timezone.now(),
            )
            send_announcement(a)
            made["announcements"] += 1

        made["message_threads"] = 0
        subjects_msg = (["About Friday pickup"] if quick else
                        ["About Friday pickup", "Field trip permission",
                         "Course of study question"])
        for subj in subjects_msg:
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

        # ── early dismissals (site-wide + one grade-specific) ───────
        made["early_dismissals"] = 0
        site_dismissal = EarlyDismissal.objects.create(
            date=today + dt.timedelta(days=3), dismissal_time=dt.time(11, 30),
            reason="Staff professional-development half-day.",
        )
        notify_early_dismissal(site_dismissal, actor=head)
        made["early_dismissals"] += 1
        EarlyDismissal.objects.create(
            date=today + dt.timedelta(days=10), dismissal_time=dt.time(12, 0),
            reason="Grade 12 university-application workshop.",
            group=homerooms_by_grade[12][0][0],
        )
        made["early_dismissals"] += 1

        # ── staff intranet chat: a few DMs + one broadcast per audience ──
        made["staff_messages"] = 0
        for sender, recipient, body, urgent in [
            (front, form_teachers[0],
             "Grade 7A pickup change for Jordan — mom will be late.", True),
            (form_teachers[0], front, "Noted, thank you — I'll let him know.", False),
            (head, front, "Can you print tomorrow's assembly programme?", False),
        ]:
            StaffMessage.objects.create(
                sender=sender, recipient=recipient, audience=StaffMessage.Audience.DIRECT,
                body=body, urgent=urgent,
            )
            made["staff_messages"] += 1
        for audience, body, sender in [
            (StaffMessage.Audience.TEACHERS,
             "Reminder: Term 1 report card comments are due Friday.", head),
            (StaffMessage.Audience.TUTORS,
             "Robotics Club room has moved to the Computer Lab this week.", front),
            (StaffMessage.Audience.ALL_STAFF,
             "Fire drill at 10:00 a.m. tomorrow — no action needed.", head),
        ]:
            StaffMessage.objects.create(
                sender=sender, recipient=None, audience=audience, body=body, urgent=False,
            )
            made["staff_messages"] += 1
        made["staffchat_cursors"] = 0
        for u in (front, form_teachers[0], head):
            StaffChatCursor.objects.get_or_create(
                user=u, defaults={"last_read_at": timezone.now() - dt.timedelta(hours=2)},
            )
            made["staffchat_cursors"] += 1

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
        # (skip any homeroom that aide is already staffing — the per-homeroom
        # loop above already rolled the dice on the same small aide pool).
        if aides:
            already = set(
                GroupStaff.objects.filter(user=aides[0]).values_list("group_id", flat=True)
            )
            candidate = next(
                (hr for hr in homerooms_flat if hr[0].id not in already), None
            )
            if candidate:
                GroupStaff.objects.create(
                    group=candidate[0], user=aides[0],
                    role=GroupStaff.Role.ASSISTANT, active=False,
                )

        # ── TOTP devices so MFA-coverage isn't 0% ───────────────────
        for u in staff_all:
            if u is head or u is front or rng.random() < 0.7:
                TOTPDevice.objects.get_or_create(
                    user=u, name="default", defaults={"confirmed": True}
                )

        # ── student portal logins for a few graduating Grade 12 pupils ──
        made["student_logins"] = 0
        senior = homerooms_by_grade.get(12, [])
        for grp, _r, _l in senior[:1]:
            for p in pupils_by_class[grp.id][:5]:
                su = User(
                    username=f"student{p.student_number}", email="",
                    role=Role.STUDENT, first_name=p.first_name, last_name=p.last_name,
                )
                su.set_password(DEMO_PASSWORD)
                su.last_login = timezone.now() - dt.timedelta(hours=rng.randint(1, 72))
                su.save()
                p.user = su
                p.save(update_fields=["user"])
                made["student_logins"] += 1

        # ── synthetic recent auth events for the security panel ─────
        ips = ["203.0.113.7", "198.51.100.22", "203.0.113.41"]
        for act, n, summ in [
            (AuditAction.LOGIN, 12, "signed in"),
            (AuditAction.LOGIN_FAILED, 6, "bad password"),
            (AuditAction.LOCKOUT, 2, "locked out after 5 attempts"),
            (AuditAction.MFA_VERIFIED, 10, "second factor accepted"),
            (AuditAction.PERMISSION_DENIED, 5, "denied /api/billing/"),
            (AuditAction.LOGOUT, 6, "signed out"),
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
                size_bytes=rng.randint(58_000_000, 74_000_000) if ok else None,
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

        # ── rubric criteria + scores on a sample of schemes ────────
        made["rubric_criteria"] = made["rubric_scores"] = 0
        crit_labels = ["Understanding", "Application", "Communication", "Effort"]
        score_rows: list[RubricScore] = []
        schemes = list(AssessmentScheme.objects.all())
        sample_schemes = schemes[:1] if quick else rng.sample(schemes, k=min(60, len(schemes)))
        for scheme in sample_schemes:
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
        RubricScore.objects.bulk_create(score_rows, batch_size=2000)
        made["rubric_scores"] = len(score_rows)

        # ── lesson resources + draft plans + a term-2 unit ─────────
        made["lesson_resources"] = 0
        for lp in LessonPlan.objects.all()[: (1 if quick else 90)]:
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.LINK,
                title="Reference slides", url="https://example.test/slides",
            )
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.NOTE, title="Teacher note",
                body="Bring the department's shared handout set.",
            )
            LessonResource.objects.create(
                lesson=lp, kind=LessonResource.Kind.FILE, title="Worksheet",
                file=ContentFile(b"Demo worksheet content.\n", name="worksheet.txt"),
            )
            made["lesson_resources"] += 3
        for grp, _r, lead in homerooms_flat[: (1 if quick else 6)]:
            u2 = CurriculumUnit.objects.create(
                group=grp, term=term2, title="Term 2 - Unit 1",
                summary="Synthetic term-2 unit.", sequence=1,
            )
            LessonPlan.objects.create(
                group=grp, unit=u2, author=lead, date=term2.start_date,
                title="Term 2 opener (draft)", objectives="Draft objectives.",
                status=LessonPlan.Status.DRAFT,
            )

        # ── IEPs on a handful of pupils across grades ──────────────
        from apps.iep.models import (
            IEP,
            IEPAccommodation,
            IEPGoal,
            IEPReview,
            IEPService,
        )

        made["ieps"] = 0
        _iep_specs = [
            ("Specific learning disability — reading fluency", IEPGoal.Area.READING),
            ("Speech / language delay", IEPGoal.Area.COMMUNICATION),
            ("ADHD — organisation and self-regulation", IEPGoal.Area.ORGANISATION),
            ("Dyscalculia — numeracy support", IEPGoal.Area.MATH),
            ("Autism spectrum — social communication support", IEPGoal.Area.SOCIAL_EMOTIONAL),
            ("Generalised anxiety — exam accommodations", IEPGoal.Area.SOCIAL_EMOTIONAL),
        ]
        iep_pupils = all_pupils[: (1 if quick else len(_iep_specs))]
        for pupil, (concern, area) in zip(iep_pupils, _iep_specs, strict=False):
            plan = IEP.objects.create(
                student=pupil, school_year=YEAR_NAME,
                status=IEP.Status.ACTIVE, primary_concern=concern,
                start_date=YEAR_START, review_date=TERM2[0],
                strengths="Engaged in hands-on tasks; strong verbal reasoning.",
                needs="Extra time and scaffolding for extended written work.",
                summary="Reviewed with the family; targets set for the year.",
                case_manager=head, created_by=head,
            )
            IEPGoal.objects.create(
                iep=plan, area=area, order=1,
                description="Meet the grade-level benchmark for the target area by June.",
                baseline="Currently below the grade-level benchmark.",
                target="Within 6 months of grade level on the spring assessment.",
                progress=IEPGoal.Progress.PROGRESSING,
                progress_notes="Steady gains through term 1.",
            )
            IEPGoal.objects.create(
                iep=plan, area=IEPGoal.Area.SOCIAL_EMOTIONAL, order=2,
                description="Use a self-regulation strategy independently when frustrated.",
                progress=IEPGoal.Progress.EMERGING,
            )
            IEPAccommodation.objects.create(
                iep=plan, category=IEPAccommodation.Category.TIMING,
                description="Extended time (1.5x) on assessments.",
                applies_to="Assessments",
            )
            IEPAccommodation.objects.create(
                iep=plan, category=IEPAccommodation.Category.PRESENTATION,
                description="Instructions given verbally and in writing; chunked tasks.",
            )
            IEPService.objects.create(
                iep=plan, service="Resource room support", provider="Ms. Okafor",
                frequency="3 x 40 min / week", location="Resource Room",
                start_date=YEAR_START,
            )
            IEPReview.objects.create(
                iep=plan, review_date=TERM1[1],
                attendees="Parent, homeroom teacher, resource teacher",
                outcome=IEPReview.Outcome.CONTINUE,
                notes="On track; continue as written.",
                next_review_date=TERM2[0], recorded_by=head,
            )
            made["ieps"] += 1

        # ── report cards: finalise (not release) a further batch ────
        for card in ReportCard.objects.filter(status=ReportCard.Status.DRAFT)[
            : (1 if quick else 180)
        ]:
            generate_report_card(card)
        made["report_cards"] = ReportCard.objects.count()

        # ── registration: waitlist rows + offers in every state ─────
        made["offers"] = made["waitlist"] = 0
        for app in Application.objects.filter(status=Application.Status.WAITLISTED):
            WaitlistEntry.objects.get_or_create(
                application=app,
                defaults={"group": entry_homeroom, "priority": rng.choice([10, 50, 100])},
            )
            made["waitlist"] += 1
        review_apps = list(
            Application.objects.filter(status=Application.Status.UNDER_REVIEW)
        )
        expires = timezone.now() + dt.timedelta(days=14)
        for i, app in enumerate(review_apps[: (1 if quick else 8)]):
            off = make_offer(
                app, group=entry_homeroom, start_date=dt.date(2027, 8, 30),
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
                child_date_of_birth=dt.date(2014, 5, 1), applicant_name="A Parent",
                applicant_email=f"{st.lower()}@example.test", status=st,
                desired_group=entry_homeroom,
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
                location=rng.choice(
                    ["cafeteria", "classroom", "gymnasium", "hallway", "science lab"]
                ),
                description=f"Synthetic {cat.lower()} incident for demo purposes.",
                action_taken="Guardians informed; monitored.",
                first_aid_given=rng.random() < 0.4, reported_by=rng.choice(all_teachers),
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
            body="We are finalising a date for the annual inter-house sports day. "
                 "Details to follow.",
            audience=Announcement.Audience.ALL_PARENTS, author=head,
        )

        # ── billing: draft / partial / void / overdue + credits ────
        made["credits"] = 0
        reg_fee = FeeSchedule.objects.get(name="Registration fee")
        for k, p in enumerate(all_pupils[: (2 if quick else 60)]):
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
        for p in all_pupils[: (1 if quick else 15)]:
            Credit.objects.create(
                student=p, amount_cents=rng.choice([2500, 5000, 7500, 10000]),
                reason="Goodwill adjustment (demo).", created_by=front,
            )
            made["credits"] += 1
        v = Invoice.objects.filter(status=Invoice.Status.ISSUED).first()
        if v:
            void_invoice(v, reason="Issued in error (demo).", actor=front)
        made["invoices"] = Invoice.objects.count()
        made["payments"] = Payment.objects.count()

        # ── booking: exercise every status + a cancelled slot ──────
        for b in list(Booking.objects.all())[: (1 if quick else 30)]:
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
        portal_links = list(
            GuardianLink.objects.filter(guardian__user__isnull=False).select_related(
                "guardian__user", "student"
            )
        )
        for i, gl in enumerate(portal_links[: (1 if quick else 12)]):
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
        for p in all_pupils[: (2 if quick else 100)]:
            Document.objects.create(
                student=p, kind=rng.choice(list(Document.Kind.values)),
                title="Scanned record (demo)", uploaded_by=front,
                file=ContentFile(b"%PDF-1.4 demo document\n", name="record.pdf"),
            )
            made["documents"] += 1
        from apps.registration.models import ApplicationDocument
        for app in Application.objects.all()[: (1 if quick else 8)]:
            ApplicationDocument.objects.create(
                application=app, title="Birth certificate (demo)", uploaded_by=front,
                file=ContentFile(b"%PDF-1.4 demo\n", name="bc.pdf"),
            )

        # ── health-access grants for aides / tutors ───────────────
        for u in (aides + tutors)[: (1 if quick else 6)]:
            HealthAccessGrant.objects.get_or_create(
                user=u,
                defaults={"granted_by": head, "reason": "Classroom support (demo)."},
            )

        # ── cancel a handful of sessions ─────────────────────────
        for occ in SessionOccurrence.objects.filter(
            status=SessionOccurrence.Status.SCHEDULED
        ).order_by("?")[: (1 if quick else 20)]:
            occ.status = SessionOccurrence.Status.CANCELLED
            occ.cancelled_reason = "Teacher absent (demo)."
            occ.save(update_fields=["status", "cancelled_reason"])

        made["guardians"] = Guardian.objects.count()
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
        from apps.iep.models import (
            IEP,
            IEPAccommodation,
            IEPGoal,
            IEPReview,
            IEPService,
        )
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
            EarlyDismissal,
            Room,
            SessionOccurrence,
            SessionTemplate,
            Term,
        )
        from apps.staffchat.models import StaffChatCursor, StaffMessage

        ordered = [
            BackupRun,
            StaffChatCursor, StaffMessage,
            IEPReview, IEPService, IEPAccommodation, IEPGoal, IEP,
            Payment, InvoiceLine, Credit, Invoice,
            RubricScore, AssessmentResult, Assessment, RubricCriterion,
            ReportCardEntry, ReportCard,
            Booking, Slot,  # AvailabilityWindow + Offering cascade from here / below
            LessonResource, LessonPlan, CurriculumUnit,
            Message, IncidentAcknowledgement, OutboundEmail,
            ContactChangeRequest,
            AttendanceRecord,
            Consent, Enrolment, Offer, WaitlistEntry, ApplicationDocument,
            SessionOccurrence, SessionTemplate, Closure, EarlyDismissal,
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

        from apps.core.models import SchoolProfile, SiteConfiguration
        SchoolProfile.objects.all().delete()
        SiteConfiguration.objects.all().delete()

    # ------------------------------------------------------------------
    def _user(self, rng, taken_usernames, role, first=None, last=None):
        fn = first or rng.choice(FIRST)
        ln = last or rng.choice(LAST)
        username = _unique_username(fn, ln, taken_usernames)
        u = User(
            username=username, email=f"{username}@example.test", role=role,
            first_name=fn, last_name=ln,
        )
        u.set_password(DEMO_PASSWORD)
        u.last_login = timezone.now() - dt.timedelta(hours=rng.randint(1, 240))
        u.last_password_change = timezone.now() - dt.timedelta(days=rng.randint(1, 120))
        u.save()
        return u

    def _make_pupil(self, rng, grp, grade_n, term1, number, teachers, taken_usernames):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        # a Grade-7 pupil is ~12, Grade-12 ~17
        age_years = 5 + grade_n + rng.choice([0, 0, 1])
        dob = dt.date(2026, 9, 1) - dt.timedelta(days=age_years * 365 + rng.randint(0, 300))
        p = Student.objects.create(
            first_name=fn, last_name=ln, date_of_birth=dob,
            student_number=f"S{number}", status=Student.Status.ENROLLED, primary_group=grp,
            pronouns=rng.choice(["she/her", "he/him", "they/them"]),
        )
        Enrolment.objects.create(student=p, group=grp, start_date=term1.start_date)

        # 1-2 guardians
        n_g = rng.choice([1, 2, 2])
        for j in range(n_g):
            rel = (GuardianLink.Relationship.MOTHER if j == 0
                   else rng.choice([GuardianLink.Relationship.FATHER,
                                    GuardianLink.Relationship.GRANDPARENT]))
            if rel == GuardianLink.Relationship.MOTHER:
                gfn = rng.choice(FEMALE_FIRST)
            elif rel == GuardianLink.Relationship.FATHER:
                gfn = rng.choice(MALE_FIRST)
            else:
                # GRANDPARENT isn't gendered in the choices list - either pool fits.
                gfn = rng.choice(FEMALE_FIRST + MALE_FIRST)
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
            phone=f"(242) 555-{rng.randint(1000, 9999)}",
            alt_phone=f"(242) 555-{rng.randint(1000, 9999)}", priority=1,
        )
        AuthorizedPickup.objects.create(
            student=p, name=f"{rng.choice(FIRST)} {ln}", relationship="grandparent",
            phone=f"(242) 555-{rng.randint(1000, 9999)}",
            note="May collect after 2:30 p.m. only.", active=True,
        )

        # deterministically cover every health table + action-plan kind
        # on the first handful of pupils; the rest are probabilistic.
        forced = number % 100_000
        if forced == 1 or rng.random() < 0.10:
            Allergy.objects.create(
                student=p, allergen=rng.choice(ALLERGENS), reaction="hives, swelling",
                severity=Allergy.Severity.ANAPHYLAXIS, epipen_required=True,
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.ANAPHYLAXIS,
                plan="Administer epinephrine, call 919, contact guardians.",
                effective_from=term1.start_date, review_by=term1.end_date,
            )
        elif rng.random() < 0.08:
            sev = rng.choice([Allergy.Severity.MILD, Allergy.Severity.MODERATE,
                              Allergy.Severity.SEVERE])
            Allergy.objects.create(
                student=p, allergen=rng.choice(ALLERGENS), reaction="rash",
                severity=sev, epipen_required=False,
            )
        if forced == 2 or rng.random() < 0.09:
            Condition.objects.create(
                student=p, name="asthma", details="exercise-induced; inhaler on file",
                diagnosed_on=dt.date(2022, 3, 1), ongoing=True,
            )
            ActionPlan.objects.create(
                student=p, kind=ActionPlan.Kind.ASTHMA,
                plan="Reliever inhaler; rest; call guardians if no improvement.",
                effective_from=term1.start_date,
            )
        if forced == 3 or rng.random() < 0.06:
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
            student=p, defaults={"blood_type": rng.choice(["O+", "A+", "B+", "AB+", "O-"])}
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

        # give a sample of families a portal login so the portal is testable —
        # deterministic for the first few pupils (so a --quick build always has
        # at least one, exercising message threads / contact-change requests),
        # probabilistic after that so it scales with the school's real size.
        if number <= 7_000_010 or rng.random() < 0.02:
            gl = p.guardian_links.filter(is_primary_contact=True).first()
            if gl and not gl.guardian.user_id:
                uname = _unique_username(
                    gl.guardian.first_name, gl.guardian.last_name, taken_usernames
                )
                pu = User(username=uname,
                          email=gl.guardian.email, role=Role.PARENT,
                          first_name=gl.guardian.first_name, last_name=gl.guardian.last_name)
                pu.set_password(DEMO_PASSWORD)
                pu.last_login = timezone.now() - dt.timedelta(hours=rng.randint(1, 240))
                pu.save()
                gl.guardian.user = pu
                gl.guardian.save(update_fields=["user"])

        return p
