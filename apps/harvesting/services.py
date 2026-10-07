import logging
import time
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
import httpx

from apps.account.models import User
from apps.catalog.models import Country, Editorial
from apps.journal.models import Journal
from apps.journal.services import create_journal
from apps.platforms.models import Platform
from . import models

logger = logging.getLogger(__name__)


def record_schedule_harvest_start(harvest: models.Harvest) -> None:
    """Registra en el Schedule el instante en que arrancó la cosecha asociada."""
    if not harvest.schedule_id or harvest.started_at is None:
        return
    schedule = harvest.schedule
    schedule.start_date = harvest.started_at
    schedule.finish_date = None
    schedule.duration = None
    schedule.save(update_fields=["start_date", "finish_date", "duration"])


def record_schedule_harvest_finish(harvest: models.Harvest) -> None:
    """Registra en el Schedule el cierre y la duración real de la cosecha asociada."""
    if not harvest.schedule_id or harvest.started_at is None or harvest.finished_at is None:
        return
    schedule = harvest.schedule
    schedule.start_date = harvest.started_at
    schedule.finish_date = harvest.finished_at
    schedule.duration = harvest.finished_at - harvest.started_at
    schedule.save(update_fields=["start_date", "finish_date", "duration"])


def get_latest_cursor_for_platform(platform: Platform) -> str:
    """
    Obtiene el api_cursor más reciente de cosechas previas de la plataforma.
    Prioriza cosechas que ya hayan avanzado con un cursor real devuelto por la API (distinto de '*').
    Si no existe ninguna cosecha con cursor previo, retorna '*' para iniciar la paginación en OpenAlex.
    """
    latest = (
        models.Harvest.objects
        .filter(platform=platform)
        .exclude(api_cursor="")
        .exclude(api_cursor="*")
        .exclude(api_cursor__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if latest and latest.api_cursor:
        return latest.api_cursor
    return "*"


class OpenAlexHarvester:
    """
    Recolector especializado para la API pública de OpenAlex (fuentes de tipo revista).

    Implementa:
    - Paginación por cursor con guardado progresivo.
    - Límites de registros y tiempo de ejecución.
    - Deduplicación por ISSN integrando create_journal.
    - Sincronización automática con la tabla intermedia SharedJournalPlatform.
    """

    DEFAULT_BASE_URL = "https://api.openalex.org"

    def __init__(
        self,
        harvest: models.Harvest,
        client: httpx.Client | None = None,
        batch_size: int = 50,
        user: Any = None,
    ):
        self.harvest = harvest
        self.batch_size = min(max(batch_size, 1), 100)
        self._custom_client = client
        self.user = user or harvest.created_by or User.all_objects.get(code=0)

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.Client(
            headers={
                "User-Agent": "UFPS-Harvester/1.0 (mailto:biblioteca@ufps.edu.co)",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def harvest_records(self) -> models.Harvest:
        """
        Ejecuta el ciclo de recolección para la cosecha configurada.
        """
        harvest = self.harvest
        platform = harvest.platform

        # Transición de estado a RUNNING
        harvest.state = models.Harvest.State.RUNNING
        is_first_start = harvest.started_at is None
        if is_first_start:
            harvest.started_at = timezone.now()
        harvest.save(update_fields=["state", "started_at"])
        if is_first_start:
            record_schedule_harvest_start(harvest)

        # Recuperar o establecer cursor
        cursor = harvest.api_cursor or get_latest_cursor_for_platform(platform)
        if not cursor or not cursor.strip():
            cursor = "*"
        harvest.api_cursor = cursor
        harvest.save(update_fields=["api_cursor"])

        start_time = time.monotonic()
        base_url = (platform.base_api_url or self.DEFAULT_BASE_URL).rstrip("/")
        sources_url = f"{base_url}/sources"

        client = self._get_client()
        should_close_client = self._custom_client is None

        try:
            while True:
                # Comprobar si fue pausada o cancelada externamente
                harvest.refresh_from_db()
                if harvest.state in [
                    models.Harvest.State.CANCELLED,
                    models.Harvest.State.PAUSED,
                ]:
                    logger.info("Cosecha #%s interrumpida con estado: %s", harvest.pk, harvest.state)
                    break

                # Comprobar límite de registros alcanzado
                total_processed = harvest.records_added + harvest.records_updated
                if harvest.max_quantity and total_processed >= harvest.max_quantity:
                    logger.info("Límite de cantidad alcanzado en cosecha #%s (%s)", harvest.pk, total_processed)
                    break

                # Comprobar límite de tiempo transcurrido
                elapsed_minutes = (time.monotonic() - start_time) / 60.0
                if harvest.stop_after_minutes and elapsed_minutes >= harvest.stop_after_minutes:
                    logger.info("Límite de tiempo alcanzado en cosecha #%s (%.2f min)", harvest.pk, elapsed_minutes)
                    break

                # Calcular tamaño del lote restante si hay max_quantity
                page_size = self.batch_size
                if harvest.max_quantity:
                    remaining = harvest.max_quantity - total_processed
                    page_size = min(page_size, remaining)

                params = {
                    "filter": "type:journal",
                    "cursor": cursor,
                    "per-page": page_size,
                }

                response = client.get(sources_url, params=params)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"OpenAlex API respondió con código {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                meta = data.get("meta", {})
                next_cursor = meta.get("next_cursor")
                results = data.get("results", [])

                if not results:
                    logger.info("No se encontraron más resultados para la cosecha #%s.", harvest.pk)
                    break

                for item in results:
                    # Chequeo de límites dentro del lote
                    current_processed = harvest.records_added + harvest.records_updated
                    if harvest.max_quantity and current_processed >= harvest.max_quantity:
                        break
                    elapsed_batch = (time.monotonic() - start_time) / 60.0
                    if harvest.stop_after_minutes and elapsed_batch >= harvest.stop_after_minutes:
                        break

                    self._process_single_source(item)

                # Actualizar cursor y métricas de progreso de forma progresiva e inalterable
                if next_cursor:
                    cursor = next_cursor
                    harvest.api_cursor = next_cursor

                harvest.save(
                    update_fields=[
                        "api_cursor",
                        "records_added",
                        "records_updated",
                        "records_failed",
                    ]
                )

                # Si no hay más páginas, finalizar
                if not next_cursor:
                    break

            # Finalización con éxito si no fue cancelada ni pausada.
            # Una pausa no cierra la cosecha: no se registra finished_at ni duration.
            harvest.refresh_from_db()
            if harvest.state == models.Harvest.State.PAUSED:
                harvest.save(
                    update_fields=[
                        "api_cursor",
                        "records_added",
                        "records_updated",
                        "records_failed",
                    ]
                )
            else:
                if harvest.state != models.Harvest.State.CANCELLED:
                    harvest.state = models.Harvest.State.COMPLETED
                harvest.finished_at = timezone.now()
                harvest.save(
                    update_fields=[
                        "state",
                        "finished_at",
                        "api_cursor",
                        "records_added",
                        "records_updated",
                        "records_failed",
                    ]
                )
                record_schedule_harvest_finish(harvest)

        except Exception as exc:
            logger.exception("Error durante la ejecución de la cosecha #%s: %s", harvest.pk, exc)
            harvest.state = models.Harvest.State.FAILED
            harvest.error_message = str(exc)
            harvest.finished_at = timezone.now()
            harvest.save(
                update_fields=[
                    "state",
                    "error_message",
                    "finished_at",
                    "api_cursor",
                    "records_added",
                    "records_updated",
                    "records_failed",
                ]
            )
            record_schedule_harvest_finish(harvest)
            raise
        finally:
            if should_close_client:
                client.close()

        return harvest

    def _process_single_source(self, item: dict[str, Any]) -> None:
        """
        Procesa una entrada de OpenAlex, extrae los datos de la revista y
        utiliza apps.journal.services.create_journal para insertar/actualizar
        garantizando deduplicación por ISSN.
        """
        harvest = self.harvest

        # Obtener ISSN preferencial (issn_l o primer ISSN de la lista)
        issn_l = item.get("issn_l")
        issn_list = item.get("issn") or []
        issn = issn_l or (issn_list[0] if issn_list else None)

        if not issn:
            harvest.records_failed += 1
            return

        title = item.get("display_name") or "Sin título"
        url_image = item.get("image_url")
        is_deprecated = item.get("is_deprecated", False)
        active = not is_deprecated
        has_apc = bool(item.get("apc_usd") or item.get("apc_prices"))
        has_full_text = bool(item.get("is_oa"))

        # Gestionar Editorial en el catálogo
        editorial_name = item.get("host_organization_name") or item.get("publisher")
        editorial_id = None
        if editorial_name and editorial_name.strip():
            clean_name = editorial_name.strip().lower()
            editorial, _ = Editorial.all_objects.get_or_create(
                name=clean_name,
                defaults={"created_by": self.user},
            )
            if editorial.is_deleted:
                editorial.restore()
            editorial_id = editorial.id

        # Gestionar País en el catálogo
        country_ids = None
        country_code = item.get("country_code")
        if country_code and country_code.strip():
            country = Country.objects.filter(abbreviation__iexact=country_code.strip()).first()
            if country:
                country_ids = [country.id]

        # Verificar si la revista ya existe para determinar si se agrega o actualiza
        compact_issn = "".join(issn.split()).replace("-", "").upper()
        formatted_issn = f"{compact_issn[:4]}-{compact_issn[4:]}" if len(compact_issn) == 8 else issn
        is_existing = Journal.all_objects.filter(issn__iexact=formatted_issn).exists()

        try:
            create_journal(
                issn=issn,
                title=title,
                user=self.user,
                editorial_id=editorial_id,
                url_image=url_image,
                has_apc=has_apc,
                active=active,
                country_ids=country_ids,
                platform_id=harvest.platform_id,
                has_full_text=has_full_text,
            )
            if is_existing:
                harvest.records_updated += 1
            else:
                harvest.records_added += 1
        except Exception as exc:
            logger.warning("Fallo al crear o actualizar revista %s: %s", issn, exc)
            harvest.records_failed += 1


def get_harvester_for_platform(harvest: models.Harvest, **kwargs) -> OpenAlexHarvester:
    """
    Factoría que selecciona el recolector adecuado según la plataforma.
    """
    platform_name = (harvest.platform.name or "").lower()
    base_url = (harvest.platform.base_api_url or "").lower()

    if "openalex" in platform_name or "openalex.org" in base_url:
        return OpenAlexHarvester(harvest, **kwargs)

    raise ValueError(
        f"No existe un motor de recolección configurado para la plataforma '{harvest.platform.name}'. "
        f"Actualmente solo se encuentra implementado el proveedor OpenAlex."
    )


def execute_harvest(harvest_id: int, **kwargs) -> models.Harvest:
    """
    Ejecuta el proceso de cosecha para el ID suministrado.
    """
    harvest = models.Harvest.objects.get(pk=harvest_id)
    harvester = get_harvester_for_platform(harvest, **kwargs)
    return harvester.harvest_records()


def run_scheduled_harvests() -> list[models.Harvest]:
    """
    Verifica los Schedules registrados y genera/ejecuta cosechas para aquellos
    que han alcanzado su próxima ejecución según la frecuencia configurada.

    Un Schedule se considera habilitado mientras no haya sido eliminado
    lógicamente (soft-delete). No existe un flag is_active aparte.
    """
    now = timezone.now()
    active_schedules = models.Schedule.objects.filter(deleted_at__isnull=True)

    executed_harvests: list[models.Harvest] = []

    for schedule in active_schedules:
        # Evitar crear cosecha si ya existe una activa para la misma plataforma
        has_active_harvest = models.Harvest.objects.filter(
            platform=schedule.platform,
            state__in=[
                models.Harvest.State.PENDING,
                models.Harvest.State.RUNNING,
                models.Harvest.State.PAUSED,
            ],
        ).exists()
        if has_active_harvest:
            continue

        last_harvest = schedule.harvests.order_by("-created_at").first()
        should_run = False

        if schedule.frequency == models.Schedule.Frequency.ONCE:
            should_run = last_harvest is None
        elif schedule.frequency == models.Schedule.Frequency.DAILY:
            should_run = last_harvest is None or last_harvest.created_at <= now - timedelta(days=1)
        elif schedule.frequency == models.Schedule.Frequency.WEEKLY:
            should_run = last_harvest is None or last_harvest.created_at <= now - timedelta(weeks=1)
        elif schedule.frequency == models.Schedule.Frequency.MONTHLY:
            should_run = last_harvest is None or last_harvest.created_at <= now - timedelta(days=30)

        if should_run:
            harvest = models.Harvest.objects.create(
                platform=schedule.platform,
                schedule=schedule,
                max_quantity=schedule.max_quantity,
                stop_after_minutes=schedule.stop_after_minutes,
                api_cursor=get_latest_cursor_for_platform(schedule.platform),
                created_by=schedule.created_by,
            )
            try:
                execute_harvest(harvest.pk)
            except Exception as exc:
                logger.error("Error al ejecutar cosecha programada #%s: %s", harvest.pk, exc)
            executed_harvests.append(harvest)

    return executed_harvests
