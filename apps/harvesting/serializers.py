from django.utils.duration import duration_string
from rest_framework import serializers

from . import models
from .services import get_latest_cursor_for_platform

AUDIT_FIELDS = (
    "id",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "deleted_by",
    "deleted_at",
    "delete_explanation",
)


class ScheduleSerializer(serializers.ModelSerializer):
    """
    Serializador para la administración y programación de cosechas (Schedule).

    El usuario solo define la plataforma, la frecuencia y los límites.
    Los campos start_date, finish_date y duration son de solo lectura:
    los registra automáticamente el motor de cosecha.
    """

    platform_name = serializers.CharField(
        source="platform.name",
        read_only=True,
    )

    class Meta:
        model = models.Schedule
        fields = [
            *AUDIT_FIELDS,
            # — El usuario define estos —
            "platform",
            "platform_name",
            "frequency",
            "max_quantity",
            "stop_after_minutes",
            # — El motor los registra automáticamente —
            "start_date",
            "finish_date",
            "duration",
        ]
        read_only_fields = [
            *AUDIT_FIELDS,
            "start_date",
            "finish_date",
            "duration",
        ]

    def validate_max_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("La cantidad máxima debe ser mayor a 0.")
        return value

    def validate_stop_after_minutes(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("El tiempo máximo debe ser mayor a 0 minutos.")
        return value

    def validate(self, attrs):
        max_quantity = attrs.get("max_quantity", getattr(self.instance, "max_quantity", None))
        stop_after_minutes = attrs.get("stop_after_minutes", getattr(self.instance, "stop_after_minutes", None))

        if max_quantity is None and stop_after_minutes is None:
            raise serializers.ValidationError(
                "Debes definir al menos un límite: cantidad máxima (max_quantity) "
                "o tiempo máximo en minutos (stop_after_minutes)."
            )

        return attrs


class HarvestSerializer(serializers.ModelSerializer):
    """
    Serializador para consultas y solicitudes de cosecha (Harvest).

    El usuario solo indica plataforma (o schedule) y los límites de la corrida.
    Estado, cursor, contadores, timestamps y duración son de solo lectura.
    """

    platform_name = serializers.CharField(
        source="platform.name",
        read_only=True,
    )
    schedule_frequency = serializers.CharField(
        source="schedule.frequency",
        read_only=True,
        default=None,
    )
    duration = serializers.SerializerMethodField(
        help_text="Tiempo real que tardó la recolección (finished_at - started_at).",
    )

    class Meta:
        model = models.Harvest
        fields = [
            *AUDIT_FIELDS,
            # — El usuario define estos —
            "platform",
            "platform_name",
            "schedule",
            "schedule_frequency",
            "max_quantity",
            "stop_after_minutes",
            # — El motor los gestiona automáticamente —
            "api_cursor",
            "state",
            "records_added",
            "records_updated",
            "records_failed",
            "started_at",
            "finished_at",
            "duration",
            "error_message",
        ]
        read_only_fields = [
            *AUDIT_FIELDS,
            "api_cursor",
            "state",
            "records_added",
            "records_updated",
            "records_failed",
            "started_at",
            "finished_at",
            "duration",
            "error_message",
        ]
        extra_kwargs = {
            "platform": {"required": False, "allow_null": True},
        }
        # El UniqueConstraint condicional de Harvest no debe exigir `platform`
        # en el payload ni duplicar el mensaje de cosecha activa (validate()).
        validators = []

    def get_duration(self, obj):
        if obj.started_at and obj.finished_at:
            return duration_string(obj.finished_at - obj.started_at)
        return None

    def validate(self, attrs):
        platform = attrs.get("platform", getattr(self.instance, "platform", None))
        schedule = attrs.get("schedule", getattr(self.instance, "schedule", None))
        max_quantity = attrs.get("max_quantity", getattr(self.instance, "max_quantity", None))
        stop_after_minutes = attrs.get("stop_after_minutes", getattr(self.instance, "stop_after_minutes", None))

        # Si se vinculó un schedule y no se enviaron límites específicos, heredar los del schedule
        if schedule is not None:
            if max_quantity is None:
                max_quantity = schedule.max_quantity
                attrs["max_quantity"] = max_quantity
            if stop_after_minutes is None:
                stop_after_minutes = schedule.stop_after_minutes
                attrs["stop_after_minutes"] = stop_after_minutes
            if platform is None:
                platform = schedule.platform
                attrs["platform"] = platform
            elif platform != schedule.platform:
                raise serializers.ValidationError({
                    "platform": (
                        f"La plataforma seleccionada ({platform}) no coincide con la "
                        f"plataforma de la programación ({schedule.platform})."
                    )
                })

        if platform is None:
            raise serializers.ValidationError({
                "platform": "Debes indicar una plataforma o una programación (schedule)."
            })

        # Al menos un límite debe estar definido
        if max_quantity is None and stop_after_minutes is None:
            raise serializers.ValidationError(
                "Debes definir al menos un límite para la cosecha: cantidad máxima "
                "(max_quantity) o tiempo máximo en minutos (stop_after_minutes)."
            )

        if max_quantity is not None and max_quantity <= 0:
            raise serializers.ValidationError({
                "max_quantity": "La cantidad máxima debe ser un entero mayor a 0."
            })

        if stop_after_minutes is not None and stop_after_minutes <= 0:
            raise serializers.ValidationError({
                "stop_after_minutes": "El tiempo máximo debe ser un entero mayor a 0 minutos."
            })

        # Verificar que no exista otra cosecha activa para la misma plataforma
        if platform is not None:
            active_qs = models.Harvest.objects.filter(
                platform=platform,
                state__in=[
                    models.Harvest.State.PENDING,
                    models.Harvest.State.RUNNING,
                    models.Harvest.State.PAUSED,
                ],
            )
            if self.instance is not None:
                active_qs = active_qs.exclude(pk=self.instance.pk)

            if active_qs.exists():
                active = active_qs.first()
                raise serializers.ValidationError({
                    "platform": (
                        f"Ya existe una cosecha activa (#{active.pk}, estado '{active.state}') "
                        f"para la plataforma '{platform.name}'."
                    )
                })

        return attrs

    def create(self, validated_data):
        platform = validated_data.get("platform")
        # El api_cursor nunca lo suministra el usuario; se obtiene automáticamente de la cosecha previa
        validated_data["api_cursor"] = get_latest_cursor_for_platform(platform)
        return super().create(validated_data)


class ExecuteHarvestRequestSerializer(serializers.Serializer):
    """Parámetros opcionales para la ejecución directa de una cosecha."""
    batch_size = serializers.IntegerField(
        required=False,
        default=50,
        min_value=1,
        max_value=100,
        help_text="Tamaño de lote para solicitudes a la API de la plataforma (1 a 100).",
    )
