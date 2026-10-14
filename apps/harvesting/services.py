import logging
import time
import calendar
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


def _source_has_apc(item: dict[str, Any]) -> bool | None:
    data_found = False
    apc_usd = item.get("apc_usd")
    if apc_usd is not None:
        try:
            amount = float(apc_usd)
            data_found = True
            if amount > 0:
                return True
        except (TypeError, ValueError):
            logger.warning("Valor apc_usd inválido de OpenAlex: %r", apc_usd)

    prices = item.get("apc_prices")
    if isinstance(prices, list):
        for price in prices:
            if not isinstance(price, dict):
                continue
            raw_amount = price.get("price", price.get("amount"))
            if raw_amount is None:
                continue
            try:
                data_found = True
                if float(raw_amount) > 0:
                    return True
            except (TypeError, ValueError):
                logger.warning("Precio APC inválido de OpenAlex: %r", raw_amount)
    return False if data_found else None


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
                "User-Agent": "UFPS-Harvester/1.0",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def harvest_records(self) -> models.Harvest:
        """
        Ejecuta el ciclo de recolección para la cosecha configurada.
        """
<<<<<<< HEAD
=======
        if not self.harvest.platform.is_harvestable:
            raise ValueError(
                f"La plataforma '{self.harvest.platform.name}' "
                "no está habilitada para cosecha (is_harvestable=false)."
            )

>>>>>>> production
        with transaction.atomic():
            harvest = models.Harvest.objects.select_for_update().get(pk=self.harvest.pk)
            if harvest.state != models.Harvest.State.PENDING:
                return harvest
            harvest.state = models.Harvest.State.RUNNING
            if harvest.started_at is None:
                harvest.started_at = timezone.now()
            harvest.save(update_fields=["state", "started_at"])
        self.harvest = harvest
        platform = harvest.platform

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
                    models.Harvest.State.PAUSING,
                    models.Harvest.State.PAUSED,
                ]:
                    logger.info("Cosecha #%s interrumpida con estado: %s", harvest.pk, harvest.state)
                    break

                # Comprobar límite de registros alcanzado
                total_processed = (
                    harvest.records_added
                    + harvest.records_updated
                    + harvest.records_failed
                )
                if harvest.max_quantity and total_processed >= harvest.max_quantity:
                    logger.info("Límite de cantidad alcanzado en cosecha #%s (%s)", harvest.pk, total_processed)
                    break

                # Comprobar límite de tiempo transcurrido
                elapsed_minutes = (
                    harvest.elapsed_seconds + time.monotonic() - start_time
                ) / 60.0
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

                page_complete = True
                for item in results:
                    # Chequeo de límites dentro del lote
                    current_processed = (
                        harvest.records_added
                        + harvest.records_updated
                        + harvest.records_failed
                    )
                    if harvest.max_quantity and current_processed >= harvest.max_quantity:
                        page_complete = False
                        break
                    elapsed_batch = (
                        harvest.elapsed_seconds + time.monotonic() - start_time
                    ) / 60.0
                    if harvest.stop_after_minutes and elapsed_batch >= harvest.stop_after_minutes:
                        page_complete = False
                        break

                    self._process_single_source(item)

                # Actualizar cursor y métricas de progreso de forma progresiva e inalterable
                if page_complete and next_cursor:
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

                if not page_complete:
                    break

                # Si no hay más páginas, finalizar
                if not next_cursor:
                    break

            # Finalización con éxito si no fue cancelada ni pausada.
            # Una pausa no cierra la cosecha: no se registra finished_at ni duration.
            harvest.refresh_from_db()
            elapsed_seconds = harvest.elapsed_seconds + int(time.monotonic() - start_time)
            if harvest.state == models.Harvest.State.PAUSING:
                harvest.state = models.Harvest.State.PAUSED
                harvest.elapsed_seconds = elapsed_seconds
                harvest.save(update_fields=["state", "elapsed_seconds"])
            if harvest.state == models.Harvest.State.PAUSED:
                harvest.elapsed_seconds = elapsed_seconds
                harvest.save(
                    update_fields=[
                        "api_cursor",
                        "records_added",
                        "records_updated",
                        "records_failed",
                        "elapsed_seconds",
                    ]
                )
            else:
                if harvest.state != models.Harvest.State.CANCELLED:
                    harvest.state = models.Harvest.State.COMPLETED
                harvest.finished_at = timezone.now()
                harvest.elapsed_seconds = elapsed_seconds
                harvest.save(
                    update_fields=[
                        "state",
                        "finished_at",
                        "api_cursor",
                        "records_added",
                        "records_updated",
                        "records_failed",
                        "elapsed_seconds",
                    ]
                )

        except Exception as exc:
            logger.exception("Error durante la ejecución de la cosecha #%s: %s", harvest.pk, exc)
            harvest.state = models.Harvest.State.FAILED
            harvest.error_message = str(exc)
            harvest.finished_at = timezone.now()
            harvest.elapsed_seconds += int(time.monotonic() - start_time)
            harvest.save(
                update_fields=[
                    "state",
                    "error_message",
                    "finished_at",
                    "api_cursor",
                    "records_added",
                    "records_updated",
                    "records_failed",
                    "elapsed_seconds",
                ]
            )
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

        title = item.get("display_name") or ""
<<<<<<< HEAD
        url_image = item.get("image_url") or item.get("image_thumbnail_url")
        active = item.get("is_active")
        if not isinstance(active, bool):
            is_deprecated = item.get("is_deprecated")
            active = not is_deprecated if isinstance(is_deprecated, bool) else None
=======
        journal_url = item.get("homepage_url")
        url_image = item.get("image_url") or item.get("image_thumbnail_url")
>>>>>>> production
        has_apc = _source_has_apc(item)
        has_full_text = item.get("is_oa")

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
<<<<<<< HEAD
                editorial_id=editorial_id,
                license=item.get("license") or None,
                url_image=url_image,
                has_apc=has_apc,
                active=active,
                country_ids=country_ids,
                platform_id=harvest.platform_id,
=======
                platform_id=harvest.platform_id,
                journal_url=journal_url,
                editorial_id=editorial_id,
                url_image=url_image,
                has_apc=has_apc,
                country_ids=country_ids,
>>>>>>> production
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
<<<<<<< HEAD
=======
    if not harvest.platform.is_harvestable:
        raise ValueError(
            f"La plataforma '{harvest.platform.name}' "
            "no está habilitada para cosecha (is_harvestable=false)."
        )

>>>>>>> production
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


def _next_occurrence(schedule: models.Schedule):
    occurrences = schedule.events.count()
    if occurrences == 0:
        return schedule.start_date

    if schedule.frequency == models.Schedule.Frequency.ONCE:
        return None
    if schedule.frequency == models.Schedule.Frequency.DAILY:
        return schedule.start_date + timedelta(days=occurrences)
    if schedule.frequency == models.Schedule.Frequency.WEEKLY:
        return schedule.start_date + timedelta(weeks=occurrences)
    if schedule.frequency == models.Schedule.Frequency.MONTHLY:
        month_index = schedule.start_date.year * 12 + schedule.start_date.month - 1 + occurrences
        year, month_index = divmod(month_index, 12)
        month = month_index + 1
        day = min(schedule.start_date.day, calendar.monthrange(year, month)[1])
        return schedule.start_date.replace(year=year, month=month, day=day)
    return None


def _run_schedule_event(event: models.ScheduleEvent) -> list[models.Harvest]:
    event.state = models.ScheduleEvent.State.RUNNING
    event.started_at = timezone.now()
    event.save(update_fields=["state", "started_at"])

    harvests = []
    failures = []
    for platform in event.schedule.platforms.all():
        with transaction.atomic():
            platform = Platform.objects.select_for_update().get(pk=platform.pk)
            active_harvest = models.Harvest.objects.filter(
                platform=platform,
                state__in=[
                    models.Harvest.State.PENDING,
                    models.Harvest.State.RUNNING,
                    models.Harvest.State.PAUSED,
                ],
            ).first()
            harvest = models.Harvest.objects.create(
                platform=platform,
                schedule=event.schedule,
                event=event,
                api_cursor=get_latest_cursor_for_platform(platform),
                max_quantity=event.schedule.max_quantity,
                stop_after_minutes=event.schedule.stop_after_minutes,
                created_by=event.schedule.created_by,
                state=(
                    models.Harvest.State.FAILED
                    if active_harvest
                    else models.Harvest.State.PENDING
                ),
                finished_at=timezone.now() if active_harvest else None,
                error_message=(
                    f"La plataforma ya tiene una cosecha activa (#{active_harvest.pk})."
                    if active_harvest
                    else None
                ),
            )
        harvests.append(harvest)
        if active_harvest:
            failures.append(harvest.error_message)
            continue
        try:
            execute_harvest(harvest.pk)
        except Exception as exc:
            logger.exception(
                "Error al ejecutar Harvest #%s del evento #%s",
                harvest.pk,
                event.pk,
            )
<<<<<<< HEAD
=======
            harvest.refresh_from_db()
            if harvest.state == models.Harvest.State.PENDING:
                harvest.state = models.Harvest.State.FAILED
                harvest.finished_at = timezone.now()
                harvest.error_message = str(exc)
                harvest.save(
                    update_fields=["state", "finished_at", "error_message"],
                )
>>>>>>> production
            failures.append(str(exc))

    event.refresh_from_db()
    event.finished_at = timezone.now()
    if failures:
        event.state = models.ScheduleEvent.State.FAILED
        event.error_message = "\n".join(failures)
    else:
        event.state = models.ScheduleEvent.State.COMPLETED
    event.save(update_fields=["state", "finished_at", "error_message"])
    return harvests


def run_scheduled_harvests(now=None) -> list[models.Harvest]:
    """Crea y procesa los eventos vencidos de schedules activos."""
    now = now or timezone.now()
    processed_harvests: list[models.Harvest] = []
    schedule_ids = models.Schedule.objects.filter(
        deleted_at__isnull=True,
        start_date__lte=now,
    ).values_list("pk", flat=True)

    for schedule_id in schedule_ids:
        with transaction.atomic():
            schedule = models.Schedule.objects.select_for_update().get(pk=schedule_id)
            if schedule.events.filter(state=models.ScheduleEvent.State.RUNNING).exists():
                continue
            scheduled_for = _next_occurrence(schedule)
            if scheduled_for is None or scheduled_for > now:
                continue
            event, created = models.ScheduleEvent.objects.get_or_create(
                schedule=schedule,
                scheduled_for=scheduled_for,
                defaults={"created_by": schedule.created_by},
            )
            if not created or event.state != models.ScheduleEvent.State.PENDING:
                continue
            event.state = models.ScheduleEvent.State.RUNNING
            event.started_at = now
            event.save(update_fields=["state", "started_at"])

        processed_harvests.extend(_run_schedule_event(event))

    return processed_harvests
