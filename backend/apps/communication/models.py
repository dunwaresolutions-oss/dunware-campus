"""
Communication — announcements, staff↔parent message threads, and structured
incident reports with a parent-acknowledgement flow.

**Email only** (docs/PII_SECURITY.md / Phase-0 decisions) — there is no SMS
path and no SMS stub. Message bodies and incident detail are
`EncryptedTextField` because a thread about a child routinely carries health,
behaviour, and custody detail; the models are `SensitiveModel` so reads are
audited.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel, SoftDeleteModel
from apps.people.models import Group, Guardian, Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})
_INSTRUCTOR_ROLES = frozenset({Role.TEACHER, Role.TUTOR})


class Announcement(SoftDeleteModel):
    class Audience(models.TextChoices):
        ALL_STAFF = "ALL_STAFF", "All staff"
        ALL_PARENTS = "ALL_PARENTS", "All parents"
        GROUP = "GROUP", "One group's parents"
        WHOLE_SITE = "WHOLE_SITE", "Everyone"

    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=12, choices=Audience.choices)
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.CASCADE, related_name="announcements"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communication_announcement"
        ordering = ["-pinned", "-published_at", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES or role in _INSTRUCTOR_ROLES:
            return True
        if role == Role.PARENT and self.published_at is not None:
            if self.audience in (self.Audience.ALL_PARENTS, self.Audience.WHOLE_SITE):
                return True
            if self.audience == self.Audience.GROUP and self.group_id:
                return Student.visible_queryset(user).filter(
                    enrolments__group_id=self.group_id, enrolments__status="ACTIVE"
                ).exists()
        return False


class MessageThread(SensitiveModel):
    subject = models.CharField(max_length=200)
    student = models.ForeignKey(
        Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="message_threads"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="message_threads"
    )
    closed = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communication_message_thread"
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self) -> str:
        return self.subject

    def is_visible_to(self, user) -> bool:
        if getattr(user, "role", None) in (Role.SUPERADMIN, Role.ADMIN):
            return True
        return self.participants.filter(pk=user.pk).exists()


class Message(BaseModel):
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = EncryptedTextField()

    class Meta:
        db_table = "communication_message"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"message in {self.thread_id}"

    def is_visible_to(self, user) -> bool:
        return self.thread.is_visible_to(user)


class IncidentReport(SensitiveModel, SoftDeleteModel):
    PII_FIELDS = ("description", "action_taken")

    class Category(models.TextChoices):
        INJURY = "INJURY", "Injury"
        BEHAVIOUR = "BEHAVIOUR", "Behaviour"
        ILLNESS = "ILLNESS", "Illness"
        ALLERGY = "ALLERGY", "Allergic reaction"
        SAFEGUARDING = "SAFEGUARDING", "Safeguarding"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent to guardians"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="incident_reports"
    )
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=150, blank=True)
    category = models.CharField(max_length=13, choices=Category.choices, default=Category.OTHER)
    severity = models.PositiveSmallIntegerField(default=1, help_text="1 minor – 5 serious")
    description = EncryptedTextField()
    action_taken = EncryptedTextField(blank=True, default="")
    first_aid_given = models.BooleanField(default=False)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    guardians_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communication_incident_report"
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["student", "occurred_at"]), models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"{self.category} incident for {self.student_id} ({self.status})"

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role in _INSTRUCTOR_ROLES:
            return self.student.is_visible_to(user)
        if role == Role.PARENT:
            return self.status != self.Status.DRAFT and self.student.is_visible_to(user)
        return False


class IncidentAcknowledgement(BaseModel):
    incident = models.ForeignKey(
        IncidentReport, on_delete=models.CASCADE, related_name="acknowledgements"
    )
    guardian = models.ForeignKey(
        Guardian, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    signature_name = models.CharField(max_length=150)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "communication_incident_ack"
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "guardian"], name="uniq_incident_ack_per_guardian"
            ),
        ]

    def __str__(self) -> str:
        return f"ack of {self.incident_id} by {self.signature_name}"


class OutboundEmail(BaseModel):
    """A log of every email Campus sent — subject + recipients + what it was
    about, never the rendered body. Lets an operator prove a guardian was
    notified without re-storing the content."""

    class Kind(models.TextChoices):
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
        INCIDENT = "INCIDENT", "Incident report"
        THREAD = "THREAD", "Message thread"
        REPORT_CARD = "REPORT_CARD", "Report card released"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    subject = models.CharField(max_length=255)
    to = models.JSONField(default=list)  # list of email addresses
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "communication_outbound_email"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} to {len(self.to)} recipient(s)"
