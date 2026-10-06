from rest_framework import serializers
from apps.core.viewset import ArchivedNameMixin
from . import models

class ScheduleSerializer(ArchivedNameMixin, serializers.ModelSerializer):

    class Meta:
        fields = [
            *AUDIT_FIELDS,
            "frequency",
            "duration",
            "start_date",
            "finish_date",
        ],
        read_only_fields = AUDIT_FIELDS

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        duration = attrs.get("duration", getattr(self.instance, "duration", None))

        if start is None or duration is None:
            return attrs

        if not isinstance(duration, timedelta):
            raise serializers.ValidationError(
                {"duration": "El formato de duración está mal."}
            )

        if duration <= timedelta(0):
            raise serializers.ValidationError(
                {"duration": "La duración debe ser mayor a 0."}
            )

        qs = Schedule.objects.filter(deleted_at__isnull=True)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        conflict = (
            qs.filter(start_date__lt=start + duration)
              .filter(start_date__gt=start - F("duration"))
              .order_by("start_date")
              .first()
        )

        if conflict is not None:
            conflict_end = conflict.start_date + conflict.duration
            raise serializers.ValidationError({
                "start_date": (
                    f"Colisiona con la programación de: #{conflict.pk} "
                    f"({conflict.start_date} → {conflict_end})."
                )
            })

        return attrs


class HarvestSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    platform = models.Platform
    schedule = models.Schedule
    class Meta:
        fields = [
            *AUDIT_FIELDS,
            "api_cursor",
            "max_quantity",
            "stop_after_minutes",
            "state",
            "records_added",
            "records_updated",
            "records_failed",
        ]

        read_only_fields = AUDIT_FIELDS
