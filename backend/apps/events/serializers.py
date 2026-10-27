from rest_framework import serializers

from apps.events.models import DeadLetterEvent, Event


class EventSerializer(serializers.ModelSerializer):
    session_id = serializers.CharField(source="session_key", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "event_id", "event_type", "version", "user_id", "session_id",
            "entity_id", "payload", "occurred_at", "processed_at",
        ]


class DeadLetterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeadLetterEvent
        fields = ["id", "event_id", "event_type", "error", "retries", "created_at", "resolved_at"]
