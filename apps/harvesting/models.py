from django.db import models

from apps.core.models import AuditableModel
from apps.platforms.models import Platform


class Schedule(AuditableModel):
    """
    Programación periódica de cosechas para una plataforma.

    El usuario define la plataforma, la frecuencia y los límites de cada ejecución.
    Los campos de tiempo (start_date, finish_date, duration) son completamente
    automáticos: los registra el motor de cosecha cada vez que ejecuta la programación.
    """

    class Frequency(models.TextChoices):
        ONCE = "once", "ONCE"
        DAILY = "daily", "DAILY"
        WEEKLY = "weekly", "WEEKLY"
        MONTHLY = "monthly", "MONTHLY"

    # ─── El usuario define esto ─────────────────────────────────────────────
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="schedules",
        help_text="Plataforma académica a la que aplica esta programación.",
    )

    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.ONCE,
        help_text="Frecuencia con la que se ejecutará la recolección.",
    )

    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Límite de registros por cosecha (opcional, obligatorio si no se define stop_after_minutes).",
    )

    stop_after_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duración máxima en minutos por cosecha (opcional, obligatorio si no se define max_quantity).",
    )

    # ─── El motor de cosecha registra esto automáticamente ─────────────────
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora en la que inició la última cosecha asociada a esta programación. Se registra automáticamente.",
    )

    finish_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora en la que terminó la última cosecha asociada. Se registra automáticamente.",
    )

    duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Tiempo total que tardó la última cosecha (finish_date - start_date). Se calcula automáticamente.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Schedule #{self.pk} - {self.platform.name} ({self.get_frequency_display()})"


class Harvest(AuditableModel):
    """
    Proceso de cosecha para una plataforma académica correspondiente a un Schedule.

    Los resultados de una cosecha son inalterables: una vez creados o completados,
    no se pueden modificar manualmente desde la API. Durante la ejecución, solo
    el motor de cosecha actualiza el cursor y los contadores de registros.
    """

    class State(models.TextChoices):
        PENDING = "pending", "PENDING"
        RUNNING = "running", "RUNNING"
        COMPLETED = "completed", "COMPLETED"
        FAILED = "failed", "FAILED"
        CANCELLED = "cancelled", "CANCELLED"
        PAUSED = "paused", "PAUSED"

    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="harvests",
        help_text="Plataforma de la cual se cosechan las revistas.",
    )

    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="harvests",
        help_text="Programación asociada a esta ejecución (opcional en ejecuciones manuales).",
    )

    api_cursor = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Cursor o token de paginación proporcionado por la API de la plataforma. Gestionado automáticamente.",
    )

    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cantidad máxima de registros a procesar en esta ejecución.",
    )

    stop_after_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Tiempo máximo en minutos antes de detener la cosecha.",
    )

    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.PENDING,
        help_text="Estado actual del ciclo de vida de la cosecha. Gestionado automáticamente.",
    )

    records_added = models.PositiveIntegerField(
        default=0,
        help_text="Cantidad de revistas nuevas insertadas.",
    )

    records_updated = models.PositiveIntegerField(
        default=0,
        help_text="Cantidad de revistas existentes actualizadas.",
    )

    records_failed = models.PositiveIntegerField(
        default=0,
        help_text="Cantidad de registros que no pudieron ser procesados o fallaron validaciones.",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora en la que inició la ejecución. Se registra automáticamente.",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora en la que finalizó o se detuvo la cosecha. Se registra automáticamente.",
    )

    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Detalle del error en caso de fallo. Se registra automáticamente.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform"],
                condition=models.Q(state__in=["pending", "running", "paused"]),
                name="unique_active_harvest_per_platform",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(max_quantity__isnull=False)
                    | models.Q(stop_after_minutes__isnull=False)
                ),
                name="harvest_requires_max_quantity_or_stop_after_minutes",
            ),
        ]

    def __str__(self):
        return f"Harvest #{self.pk} - {self.platform.name} [{self.get_state_display()}]"
