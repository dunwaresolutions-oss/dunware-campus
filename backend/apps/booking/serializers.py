from __future__ import annotations

from rest_framework import serializers

from .models import AvailabilityWindow, Booking, Offering, Slot


class OfferingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offering
        fields = ["id", "title", "kind", "description", "provider", "room",
                  "duration_minutes", "capacity_per_slot", "cancellation_hours",
                  "price_cents", "active", "created_at"]


class AvailabilityWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityWindow
        fields = ["id", "offering", "weekday", "start_time", "end_time",
                  "valid_from", "valid_to", "active"]


class SlotSerializer(serializers.ModelSerializer):
    seats_left = serializers.IntegerField(read_only=True)
    confirmed_count = serializers.IntegerField(read_only=True)
    offering_title = serializers.CharField(source="offering.title", read_only=True)

    class Meta:
        model = Slot
        fields = ["id", "offering", "offering_title", "window", "starts_at", "ends_at",
                  "capacity", "status", "seats_left", "confirmed_count"]
        read_only_fields = ["status"]


class BookingSerializer(serializers.ModelSerializer):
    booked_by = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    offering_title = serializers.CharField(source="slot.offering.title", read_only=True)
    starts_at = serializers.DateTimeField(source="slot.starts_at", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "slot", "student", "student_name", "offering_title", "starts_at",
                  "booked_by", "status", "waitlist_position", "cancelled_at",
                  "cancellation_note", "created_at"]
        read_only_fields = ["status", "waitlist_position", "cancelled_at"]
