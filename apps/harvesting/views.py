from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import AuditableViewSet, get_acting_user
from . import filters, models, serializers, services


# ==============================================================================
# SCHEDULE VIEWSET
# ==============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="Listar programaciones",
        description="Obtiene el listado de programaciones de cosecha activas.",
        tags=["Cosecha - Programaciones"],
    ),
    retrieve=extend_schema(
        summary="Consultar programación",
        description="Obtiene los detalles de una programación por su ID.",
        tags=["Cosecha - Programaciones"],
    ),
    create=extend_schema(
        summary="Crear programación",
        description="Registra una nueva programación periódica de cosecha para una plataforma.",
        tags=["Cosecha - Programaciones"],
    ),
    update=extend_schema(
        summary="Actualizar programación",
        description="Actualiza completamente los datos de una programación existente.",
        tags=["Cosecha - Programaciones"],
    ),
    partial_update=extend_schema(
        summary="Actualizar parcialmente programación",
        description="Modifica atributos específicos de una programación existente.",
        tags=["Cosecha - Programaciones"],
    ),
    destroy=extend_schema(
        summary="Eliminar programación",
        description="Aplica borrado lógico sobre la programación de cosecha.",
        tags=["Cosecha - Programaciones"],
    ),
)
class ScheduleViewSet(AuditableViewSet):
    """
    Controlador para programaciones de cosechas.
    Permite creación, consulta, modificación y borrado lógico auditado.
    """

    queryset = models.Schedule.objects.select_related("platform").all()
    serializer_class = serializers.ScheduleSerializer
    filterset_class = filters.ScheduleFilter
    search_fields = ["platform__name"]
    ordering_fields = ["created_at", "start_date", "finish_date"]
    ordering = ["-created_at"]

    @extend_schema(
        summary="Ejecutar cosecha inmediata desde programación",
        description="Crea y ejecuta de inmediato una cosecha asociada a esta programación.",
        responses={201: serializers.HarvestSerializer},
        tags=["Cosecha - Programaciones"],
    )
    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, pk=None):
        schedule = self.get_object()
        user = get_acting_user(request)

        # Verificar si ya existe una cosecha activa para la plataforma
        active_harvest = models.Harvest.objects.filter(
            platform=schedule.platform,
            state__in=[
                models.Harvest.State.PENDING,
                models.Harvest.State.RUNNING,
                models.Harvest.State.PAUSED,
            ],
        ).first()

        if active_harvest:
            return Response(
                {
                    "detail": (
                        f"Ya existe una cosecha activa (#{active_harvest.pk}, estado '{active_harvest.state}') "
                        f"para la plataforma '{schedule.platform.name}'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cursor = services.get_latest_cursor_for_platform(schedule.platform)

        harvest = models.Harvest.objects.create(
            platform=schedule.platform,
            schedule=schedule,
            api_cursor=cursor,
            max_quantity=schedule.max_quantity,
            stop_after_minutes=schedule.stop_after_minutes,
            created_by=user,
        )

        try:
            services.execute_harvest(harvest.pk, user=user)
        except Exception as exc:
            harvest.refresh_from_db()
            return Response(
                {
                    "detail": f"Error durante la ejecución de la cosecha: {exc}",
                    "harvest": serializers.HarvestSerializer(harvest).data,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        harvest.refresh_from_db()
        return Response(
            serializers.HarvestSerializer(harvest).data,
            status=status.HTTP_201_CREATED,
        )


# ==============================================================================
# HARVEST VIEWSET (INALTERABLE)
# ==============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="Listar cosechas",
        description=(
            "Obtiene el historial inalterable de ejecuciones de cosecha. "
            "Soporta filtros por plataforma, schedule, estado y fechas."
        ),
        tags=["Cosecha - Ejecuciones"],
    ),
    retrieve=extend_schema(
        summary="Consultar cosecha",
        description="Obtiene el detalle inalterable de una cosecha y sus resultados.",
        tags=["Cosecha - Ejecuciones"],
    ),
    create=extend_schema(
        summary="Solicitar nueva cosecha",
        description=(
            "Crea un nuevo registro de cosecha para una plataforma académica. "
            "El cursor de paginación lo recupera el backend; estado, contadores "
            "y fechas de ejecución no los envía el usuario. "
            "Los resultados son inalterables y no admiten PUT/PATCH manual."
        ),
        tags=["Cosecha - Ejecuciones"],
    ),
)
class HarvestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Controlador para ejecuciones de cosecha (Harvest).

    Garantiza la inalterabilidad de los resultados:
    - No admite peticiones PUT, PATCH ni DELETE por parte de clientes.
    - El progreso (api_cursor, registros agregados, actualizados y fallidos)
      solo es modificado de forma segura por el motor de recolección en services.py.
    """

    queryset = models.Harvest.objects.select_related("platform", "schedule").all()
    serializer_class = serializers.HarvestSerializer
    filterset_class = filters.HarvestFilter
    search_fields = ["platform__name"]
    ordering_fields = ["created_at", "started_at", "finished_at", "records_added"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        acting_user = get_acting_user(self.request)
        serializer.save(created_by=acting_user)

    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Los resultados de las cosechas son inalterables y no pueden ser modificados directamente."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Los resultados de las cosechas son inalterables y no pueden ser modificados directamente."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Los registros de cosechas son inalterables y no pueden ser eliminados."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(
        summary="Ejecutar cosecha",
        description="Dispara la recolección activa para una cosecha en estado PENDING.",
        request=serializers.ExecuteHarvestRequestSerializer,
        responses={200: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, pk=None):
        harvest = self.get_object()

        if harvest.state in [
            models.Harvest.State.COMPLETED,
            models.Harvest.State.CANCELLED,
        ]:
            return Response(
                {
                    "detail": (
                        f"La cosecha ya se encuentra en estado '{harvest.get_state_display()}' "
                        f"y es inalterable. Para una nueva recolección cree otra solicitud."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if harvest.state == models.Harvest.State.RUNNING:
            return Response(
                {"detail": "La cosecha ya se encuentra en ejecución activa."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = serializers.ExecuteHarvestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch_size = serializer.validated_data.get("batch_size", 50)
        acting_user = get_acting_user(request)

        try:
            services.execute_harvest(harvest.pk, batch_size=batch_size, user=acting_user)
        except Exception as exc:
            harvest.refresh_from_db()
            return Response(
                {
                    "detail": f"Ocurrió un error durante la cosecha: {exc}",
                    "harvest": serializers.HarvestSerializer(harvest).data,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        harvest.refresh_from_db()
        return Response(serializers.HarvestSerializer(harvest).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Cancelar cosecha",
        description="Cancela una cosecha que se encuentre pendiente o en ejecución.",
        responses={200: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        harvest = self.get_object()
        if harvest.state in [
            models.Harvest.State.COMPLETED,
            models.Harvest.State.CANCELLED,
            models.Harvest.State.FAILED,
        ]:
            return Response(
                {
                    "detail": (
                        f"No es posible cancelar una cosecha en estado '{harvest.get_state_display()}'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        harvest.state = models.Harvest.State.CANCELLED
        harvest.finished_at = timezone.now()
        harvest.save(update_fields=["state", "finished_at"])
        services.record_schedule_harvest_finish(harvest)
        return Response(serializers.HarvestSerializer(harvest).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Pausar cosecha",
        description="Pausa una cosecha actualmente en ejecución.",
        responses={200: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        harvest = self.get_object()
        if harvest.state != models.Harvest.State.RUNNING:
            return Response(
                {"detail": "Solo es posible pausar una cosecha en ejecución activa (running)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        harvest.state = models.Harvest.State.PAUSED
        harvest.save(update_fields=["state"])
        return Response(serializers.HarvestSerializer(harvest).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Reanudar cosecha pausada",
        description="Reanuda la ejecución de una cosecha pausada utilizando su último api_cursor.",
        responses={200: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        harvest = self.get_object()
        if harvest.state != models.Harvest.State.PAUSED:
            return Response(
                {"detail": "Solo es posible reanudar una cosecha que esté pausada (paused)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        acting_user = get_acting_user(request)
        try:
            services.execute_harvest(harvest.pk, user=acting_user)
        except Exception as exc:
            harvest.refresh_from_db()
            return Response(
                {
                    "detail": f"Error al reanudar la cosecha: {exc}",
                    "harvest": serializers.HarvestSerializer(harvest).data,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        harvest.refresh_from_db()
        return Response(serializers.HarvestSerializer(harvest).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Reintentar cosecha fallida",
        description=(
            "Genera una nueva cosecha para la plataforma a partir del último api_cursor "
            "alcanzado por la cosecha fallida, preservando la inalterabilidad de los registros."
        ),
        responses={201: serializers.HarvestSerializer},
        tags=["Cosecha - Ejecuciones"],
    )
    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        harvest = self.get_object()
        if harvest.state not in [models.Harvest.State.FAILED, models.Harvest.State.CANCELLED]:
            return Response(
                {"detail": "Solo se pueden reintentar cosechas en estado fallido o cancelado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        acting_user = get_acting_user(request)
        # Crear nueva cosecha para no alterar la fallida
        new_harvest = models.Harvest.objects.create(
            platform=harvest.platform,
            schedule=harvest.schedule,
            api_cursor=harvest.api_cursor or services.get_latest_cursor_for_platform(harvest.platform),
            max_quantity=harvest.max_quantity,
            stop_after_minutes=harvest.stop_after_minutes,
            created_by=acting_user,
        )

        return Response(
            serializers.HarvestSerializer(new_harvest).data,
            status=status.HTTP_201_CREATED,
        )
