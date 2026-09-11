from __future__ import annotations

from rest_framework import serializers

from .models import CurriculumUnit, LessonPlan, LessonResource


class CurriculumUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumUnit
        fields = ["id", "group", "term", "title", "summary", "sequence", "created_at"]


class LessonResourceSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True, default="")

    class Meta:
        model = LessonResource
        fields = ["id", "group", "group_name", "lesson", "lesson_title", "kind", "title",
                  "url", "file", "body"]
        extra_kwargs = {"group": {"required": False}}

    def validate(self, attrs):
        group = attrs.get("group") or getattr(self.instance, "group", None)
        lesson = attrs["lesson"] if "lesson" in attrs else getattr(self.instance, "lesson", None)
        if not group and not lesson:
            raise serializers.ValidationError(
                {"group": "Pick a group, or a lesson plan (its group is used)."}
            )
        if not group:
            attrs["group"] = lesson.group
        return attrs


class LessonPlanSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)
    resources = LessonResourceSerializer(many=True, read_only=True)

    class Meta:
        model = LessonPlan
        fields = ["id", "group", "unit", "date", "title", "objectives", "body",
                  "status", "author", "resources", "created_at", "updated_at"]
