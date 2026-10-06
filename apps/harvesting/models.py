from django.db import models

from apps.core.models import AuditableModel
from apps.platform.models import Platform

class Schedule(AuditableModel):

    class Frequency(models.TextChoices):
        ONCE = "once", "ONCE"
        DAILY = "daily", "DAILY"
        WEEKLY = "weekly", "WEEKLY"
        MONTHLY = "monthly", "MONTHLY"

    frequency = models.CharField(
            max_length=20,
            choices=Frequency.choices,
            default=Frequency.PENDING,
    )
    duration = models.TimeField()
    start_date = models.DateTimeField()
    finish_date = models.DateTImeField(Null=True, blank=True)

    class Meta: 
        ordering = ["-start_date"]
        constraints = []

    def __str__(self):
        return f"Schedule #{self.pk} ({self.frequency})"


class Harvest(AuditableModel): 

    class State(models.TextChoices):
        PENDING = "pending", "PENDING"
        RUNNING = "running", "RUNNING"
        COMPLETED = "completed", "COMPLETED"
        FAILED = "failed", "FAILED"
        CANCELLED = "cancelled", "CANCELLED"
        PAUSED = "paused", "PAUSED"

    platform = models.ForeignKey(
        Platforms,
        on_delete=models.PROTECT,
        null=False,
    )

    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    api_cursor = models.CharField(blank=True)
    max_quantity = models.PositiveIntegerField(null=True, blank=True)
    stop_after_minutes = models.PositiveIntegerField(null=True, blank=True)
    state = models.CharField(
            max_length=20,
            choices=State.choices,
            default=State.PENDING,
    )

    records_added = models.PositiveIntegerField()
    records_updated = models.PositiveIntegerField()
    records_failed = models.PositiveIntegerField()

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
        return f"Harvest #{self.pk} - {self.get_state_display()}"
