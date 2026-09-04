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

    class Meta:
        model = AssessmentResult
        fields = ["id", "assessment", "student", "mark", "level", "narrative",
                  "graded_by", "rubric_scores", "created_at"]


class ReportCardEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCardEntry
        fields = ["id", "report_card", "subject", "group", "mark", "level", "comment", "order"]


class ReportCardSerializer(serializers.ModelSerializer):
    entries = ReportCardEntrySerializer(many=True, read_only=True)
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields = ["id", "student", "term", "status", "summary_narrative", "entries",
                  "document_url", "generated_at", "released_at", "created_at"]
        read_only_fields = ["status", "generated_at", "released_at"]

    def get_document_url(self, obj) -> str | None:
        if not obj.document:
            return None
        request = self.context.get("request")
        url = obj.document.url
        return request.build_absolute_uri(url) if request else url
