import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import AuditableViewSet, get_acting_user
from . import filters, models, serializers
from . import services

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="Listar programaciones de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    retrieve=extend_schema(
        summary="Consultar programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    create=extend_schema(
        summary="Crear programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    update=extend_schema(
        summary="Actualizar programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    partial_update=extend_schema(
        summary="Actualizar parcialmente programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
    destroy=extend_schema(
        summary="Desactivar programación de cosecha",
        tags=["Cosecha - Programaciones"],
    ),
)
class ScheduleViewSet(AuditableViewSet):
    queryset = models.Schedule.objects.prefetch_related("platforms").all()
    serializer_class = serializers.ScheduleSerializer
    filterset_class = filters.ScheduleFilter
    search_fields = ["platforms__name"]
    ordering_fields = ["created_at", "start_date"]
    ordering = ["-created_at"]


class ScheduleEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.ScheduleEvent.objects.select_related("schedule").prefetch_related(
        "harvests",
    )
    serializer_class = serializers.ScheduleEventSerializer
    filterset_fields = ["schedule", "state"]
    ordering_fields = ["scheduled_for", "started_at", "finished_at"]
    ordering = ["-scheduled_for"]


class HarvestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.Harvest.objects.select_related(
        "platform",
        "schedule",
        "event",
    ).all()
    serializer_class = serializers.HarvestSerializer
    filterset_class = filters.HarvestFilter
    search_fields = ["platform__name"]
    ordering_fields = ["created_at", "started_at", "finished_at", "records_added"]
    ordering = ["-created_at"]

    @extend_schema(
        summary="Pausar una cosecha",
        description=(
            "Solicita detener la cosecha al terminar la página de OpenAlex que "
            "está procesando. Una cosecha pendiente se pausa inmediatamente."
        ),
        responses={200: serializers.HarvestSerializer, 202: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        with transaction.atomic():
            harvest = get_object_or_404(
                self.get_queryset().select_for_update(),
                pk=pk,
            )
            if harvest.state == models.Harvest.State.PENDING:
                harvest.state = models.Harvest.State.PAUSED
            elif harvest.state == models.Harvest.State.RUNNING:
                harvest.state = models.Harvest.State.PAUSING
            else:
                return Response(
                    {"detail": f"No se puede pausar una cosecha en estado '{harvest.state}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            harvest.updated_by = get_acting_user(request)
            harvest.updated_at = timezone.now()
            harvest.save(update_fields=["state", "updated_by", "updated_at"])

        response_status = (
            status.HTTP_202_ACCEPTED
            if harvest.state == models.Harvest.State.PAUSING
            else status.HTTP_200_OK
        )
        return Response(serializers.HarvestSerializer(harvest).data, status=response_status)

    @extend_schema(
        summary="Reanudar una cosecha pausada",
        description="Continúa la recolección desde el cursor guardado en el Harvest.",
        responses={200: serializers.HarvestSerializer, 500: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        with transaction.atomic():
            harvest = get_object_or_404(
                self.get_queryset().select_for_update(),
                pk=pk,
            )
            if harvest.state != models.Harvest.State.PAUSED:
                return Response(
                    {
                        "detail": (
                            "Solo se pueden reanudar cosechas en estado "
                            f"'{models.Harvest.State.PAUSED}'."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            harvest.state = models.Harvest.State.PENDING
            harvest.error_message = None
            harvest.updated_by = get_acting_user(request)
            harvest.updated_at = timezone.now()
            harvest.save(
                update_fields=[
                    "state",
                    "error_message",
                    "updated_by",
                    "updated_at",
                ]
            )

        try:
            harvest = services.execute_harvest(
                harvest.pk,
                user=get_acting_user(request),
            )
        except Exception as exc:
            logger.exception("Error al reanudar la cosecha #%s", harvest.pk)
            harvest.refresh_from_db()
            if harvest.state == models.Harvest.State.PENDING:
                harvest.state = models.Harvest.State.PAUSED
                harvest.error_message = str(exc)
                harvest.save(update_fields=["state", "error_message"])
            return Response(
                {
                    "detail": f"Error al reanudar la cosecha: {exc}",
                    "harvest": serializers.HarvestSerializer(harvest).data,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        harvest.refresh_from_db()
        return Response(serializers.HarvestSerializer(harvest).data)
