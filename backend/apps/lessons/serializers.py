from __future__ import annotations

from rest_framework import serializers

from .models import CurriculumUnit, LessonPlan, LessonResource


class CurriculumUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumUnit
        fields = ["id", "group", "term", "title", "summary", "sequence", "created_at"]


class LessonResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonResource
        fields = ["id", "lesson", "kind", "title", "url", "file", "body"]


class LessonPlanSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)
    resources = LessonResourceSerializer(many=True, read_only=True)

    class Meta:
        model = LessonPlan
        fields = ["id", "group", "unit", "date", "title", "objectives", "body",
                  "status", "author", "resources", "created_at", "updated_at"]
