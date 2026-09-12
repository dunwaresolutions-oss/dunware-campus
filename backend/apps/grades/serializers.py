from __future__ import annotations

from rest_framework import serializers

from .models import (
    Assessment,
    AssessmentResult,
    AssessmentScheme,
    ReportCard,
    ReportCardEntry,
    RubricCriterion,
    RubricScore,
)


class RubricCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricCriterion
        fields = ["id", "scheme", "label", "descriptor", "order", "max_level"]


class AssessmentSchemeSerializer(serializers.ModelSerializer):
    criteria = RubricCriterionSerializer(many=True, read_only=True)

    class Meta:
        model = AssessmentScheme
        fields = ["id", "group", "term", "name", "kind", "criteria", "created_at"]


class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = ["id", "scheme", "group", "title", "date", "max_mark", "released",
                  "released_at", "created_at"]
        read_only_fields = ["released", "released_at"]


class RubricScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricScore
        fields = ["id", "result", "criterion", "level"]


class AssessmentResultSerializer(serializers.ModelSerializer):
    graded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    rubric_scores = RubricScoreSerializer(many=True, read_only=True)
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = AssessmentResult
        fields = ["id", "assessment", "assessment_title", "student", "student_name",
                  "mark", "level", "narrative", "graded_by", "rubric_scores", "created_at"]


class ReportCardEntrySerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True, default="")

    class Meta:
        model = ReportCardEntry
        fields = ["id", "report_card", "subject", "group", "group_name", "mark",
                  "level", "comment", "order"]


class ReportCardSerializer(serializers.ModelSerializer):
    entries = ReportCardEntrySerializer(many=True, read_only=True)
    document_url = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    class Meta:
        model = ReportCard
        fields = ["id", "student", "student_name", "term", "term_name", "status",
                  "summary_narrative", "entries", "document_url", "generated_at",
                  "released_at", "created_at"]
        read_only_fields = ["status", "generated_at", "released_at"]

    def get_document_url(self, obj) -> str | None:
        # NOT obj.document.url: that's a bare /media/... path — nothing serves
        # /media/ directly in production, and the file is encrypted at rest
        # besides, so it must come back out through ReportCardViewSet.document.
        if not obj.document:
            return None
        request = self.context.get("request")
        path = f"/api/report-cards/{obj.pk}/document/"
        return request.build_absolute_uri(path) if request else path
