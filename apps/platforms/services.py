import ipaddress
import socket
from typing import cast
from urllib.parse import urlsplit

import httpx
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import models


LINK_CHECK_TIMEOUT_SECONDS = 10.0

# Estos códigos indican que el servidor/recurso existe,
# aunque requiera autenticación o restrinja el acceso.
LINK_ACTIVE_AUTH_STATUSES = {401, 403}
LINK_LOG_ORDERING = ("-last_check", "-created_at", "-pk")


def latest_platform_link_log(platform):
    """Retorna el último log no eliminado de la URL general."""
    prefetched = getattr(platform, "_public_link_logs", None)
    if prefetched is not None:
        return prefetched[0] if prefetched else None

    return (
        models.LinkCheckLog.objects
        .filter(platform=platform, journal_platform__isnull=True)
        .order_by(*LINK_LOG_ORDERING)
        .first()
    )


def latest_journal_link_log(journal_platform):
    """Retorna el último log no eliminado de una revista-plataforma."""
    prefetched = getattr(journal_platform, "_journal_link_logs", None)
    if prefetched is not None:
        return prefetched[0] if prefetched else None

    return (
        models.LinkCheckLog.objects
        .filter(journal_platform=journal_platform)
        .order_by(*LINK_LOG_ORDERING)
        .first()
    )


REQUIRED_PLATFORM_RELATIONS = (
    (
        "institutions",
        models.SharedPlatformSupport,
        "institution",
        "una institución responsable activa asociada",
    ),
    (
        "countries",
        models.SharedPlatformCountry,
        "country",
        "un país activo asociado",
    ),
    (
        "material_types",
        models.SharedPlatformMaterialType,
        "material_type",
        "un tipo de material activo asociado",
    ),
    (
        "languages",
        models.SharedPlatformLanguage,
        "language",
        "un idioma activo asociado",
    ),
)


def validate_platform_for_publication(
    platform: models.Platform,
) -> None:
    """
    Valida que la plataforma pueda pasar de borrador a publicado.
    """

    errors = {}

    if platform.is_deleted:
        errors["detail"] = (
            "No se puede publicar una plataforma que se encuentra eliminada."
        )

    if platform.status != models.Platform.Status.BORRADOR:
        errors["status"] = (
            "Solo una plataforma en borrador puede publicarse."
        )

    if not platform.name or not platform.name.strip():
        errors["name"] = (
            "La plataforma debe tener un nombre."
        )

    # La URL pública es independiente de base_api_url.
    # Debe existir al menos una verificación registrada en el historial.
    if not models.LinkCheckLog.objects.filter(
        platform=platform,
        journal_platform__isnull=True,
    ).exists():
        errors["url"] = (
            "La plataforma debe tener una URL pública registrada "
            "en el historial de verificación de enlaces."
        )

    # Una API Key solamente tiene sentido si existe una API base.
    if platform.encrypted_api_key:
        if not platform.base_api_url or not platform.base_api_url.strip():
            errors["base_api_url"] = (
                "La plataforma debe tener una URL de API "
                "si tiene una API Key configurada."
            )

    # Si no tiene API Key, base_api_url es completamente opcional.

    if not platform.start_period:
        errors["start_period"] = (
            "La plataforma debe indicar el inicio del período de cobertura."
        )

    if (
        platform.start_period
        and platform.finish_period
        and platform.finish_period < platform.start_period
    ):
        errors["finish_period"] = (
            "El período final no puede ser anterior al período inicial."
        )

    if not platform.valid_sintaxis_id:
        errors["valid_sintaxis"] = (
            "La plataforma debe tener una sintaxis de búsqueda asociada."
        )

    elif not models.ValidSintaxis.objects.filter(
        pk=platform.valid_sintaxis_id,
    ).exists():
        errors["valid_sintaxis"] = (
            "La sintaxis de búsqueda asociada no se encuentra activa."
        )

    from apps.journal.models import SharedJournalPlatform

    has_eligible_journals = SharedJournalPlatform.objects.filter(
        platform=platform,
        journal__deleted_at__isnull=True,
        journal__active=True,
        journal__validated_at__isnull=False,
    ).exists()
    if has_eligible_journals:
        if not models.SharedPlatformAcademicProgram.objects.filter(
            platform=platform,
            academic_program__deleted_at__isnull=True,
        ).exists():
            errors["academic_programs"] = (
                "Las revistas elegibles deben aportar al menos un programa académico."
            )
        if not models.SharedPlatformKnowledgeArea.objects.filter(
            platform=platform,
            knowledge_area__deleted_at__isnull=True,
        ).exists():
            errors["knowledge_areas"] = (
                "Las revistas elegibles deben aportar al menos un área del conocimiento."
            )

    for (
        field_name,
        through_model,
        relation_field,
        label,
    ) in REQUIRED_PLATFORM_RELATIONS:

        has_active_relation = through_model.objects.filter(
            platform=platform,
            **{
                f"{relation_field}__deleted_at__isnull": True,
            },
        ).exists()

        if not has_active_relation:
            errors[field_name] = (
                f"La plataforma debe tener al menos {label}."
            )

    if errors:
        raise ValidationError(errors)


def validate_platform_for_obsolete(
    platform: models.Platform,
) -> None:
    """
    Valida que una plataforma pueda pasar de publicado a obsoleto.
    """

    errors = {}

    if platform.is_deleted:
        errors["detail"] = (
            "No se puede modificar una plataforma que se encuentra eliminada."
        )

    if platform.status != models.Platform.Status.PUBLICADO:
        errors["status"] = (
            "Solo una plataforma publicada puede marcarse como obsoleta."
        )

    if errors:
        raise ValidationError(errors)


def validate_platform_for_reactivation(
    platform: models.Platform,
) -> None:
    """
    Valida que una plataforma pueda regresar de obsoleto a borrador.
    """

    errors = {}

    if platform.is_deleted:
        errors["detail"] = (
            "No se puede reactivar una plataforma que se encuentra eliminada."
        )

    if platform.status != models.Platform.Status.OBSOLETO:
        errors["status"] = (
            "Solo una plataforma obsoleta puede regresar a borrador."
        )

    if errors:
        raise ValidationError(errors)


def _is_successful_link_status(
    status_code: int,
) -> bool:
    """
    Determina si un código HTTP representa un enlace disponible.

    Se consideran disponibles:
    - 2xx: respuesta exitosa.
    - 3xx: recurso existente con redirección.
    - 401: recurso existente que requiere autenticación.
    - 403: recurso existente con acceso restringido.
    """

    return (
        200 <= status_code < 400
        or status_code in LINK_ACTIVE_AUTH_STATUSES
    )


def _is_public_ip_address(
    raw_address: str,
) -> bool:
    """
    Determina si una dirección IP es públicamente enrutable.

    Se utiliza como protección para evitar que la verificación
    de enlaces consulte recursos internos del servidor.
    """

    try:
        address = ipaddress.ip_address(
            raw_address.split("%", 1)[0]
        )
    except ValueError:
        return False

    return (
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
    )


def _validate_safe_http_url(
    url: str,
    *,
    field_name: str = "url",
) -> None:
    """
    Valida que una URL pueda consultarse de forma segura.

    Solo admite HTTP/HTTPS y bloquea destinos locales,
    privados, reservados o no públicamente enrutables.
    """

    try:
        parsed_url = urlsplit(url)
        port = parsed_url.port
    except ValueError:
        raise ValidationError({
            field_name: (
                "La URL configurada no es válida."
            )
        })

    if parsed_url.scheme.lower() not in {"http", "https"}:
        raise ValidationError({
            field_name: (
                "La URL debe utilizar el protocolo HTTP o HTTPS."
            )
        })

    hostname = parsed_url.hostname

    if not hostname:
        raise ValidationError({
            field_name: (
                "La URL debe contener un nombre de host válido."
            )
        })

    if parsed_url.username or parsed_url.password:
        raise ValidationError({
            field_name: (
                "La URL no puede contener credenciales embebidas."
            )
        })

    hostname = hostname.rstrip(".").lower()

    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        raise ValidationError({
            field_name: (
                "La URL no puede apuntar a un recurso local."
            )
        })

    try:
        direct_ip = ipaddress.ip_address(hostname)
    except ValueError:
        direct_ip = None

    if direct_ip is not None:
        if not _is_public_ip_address(hostname):
            raise ValidationError({
                field_name: (
                    "La URL no puede apuntar a una dirección IP "
                    "privada, local o reservada."
                )
            })

        return

    if port is None:
        port = 443 if parsed_url.scheme.lower() == "https" else 80

    try:
        address_info = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, socket.herror, OSError):
        # Un fallo DNS representa indisponibilidad del enlace,
        # no necesariamente una URL insegura.
        # httpx registrará posteriormente el fallo de conexión.
        return

    resolved_addresses: set[str] = {
        cast(str, item[4][0])
        for item in address_info
    }

    for resolved_address in resolved_addresses:
        if not _is_public_ip_address(resolved_address):
            raise ValidationError({
                field_name: (
                    "La URL resuelve a una dirección de red "
                    "privada, local o reservada."
                )
            })


def _get_next_fail_count(
    platform: models.Platform,
    *,
    url: str,
    is_active: bool,
) -> int:
    """
    Calcula la cantidad de fallos consecutivos para una URL específica.

    Una verificación exitosa reinicia el contador a cero.
    Si cambia la URL pública, la nueva URL inicia una secuencia independiente.
    """

    if is_active:
        return 0

    latest_log = (
        models.LinkCheckLog.objects
        .filter(
            platform=platform,
            journal_platform__isnull=True,
            url=url,
        )
        .order_by(*LINK_LOG_ORDERING)
        .first()
    )

    if latest_log and not latest_log.is_active:
        return latest_log.fail_count + 1

    return 1


def _perform_link_check(
    url: str,
) -> tuple[int | None, bool]:
    """
    Ejecuta la petición HTTP para comprobar la disponibilidad
    de un enlace.

    No sigue redirecciones automáticamente. Una respuesta 3xx
    ya demuestra que el servidor respondió y evita consultar
    destinos de redirección no validados.
    """

    try:
        with httpx.Client(
            timeout=LINK_CHECK_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            with client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "RABD-LinkChecker/1.0",
                },
            ) as response:
                status_code = response.status_code

        return (
            status_code,
            _is_successful_link_status(status_code),
        )

    except (
        httpx.HTTPError,
        Exception,
    ):
        return None, False


@transaction.atomic
def publish_platform(
    *,
    platform: models.Platform,
    user,
) -> models.Platform:
    """
    Publica una plataforma previamente validada.
    """

    platform = (
        models.Platform.all_objects
        .select_for_update()
        .get(pk=platform.pk)
    )

    validate_platform_for_publication(platform)

    now = timezone.now()

    platform.status = models.Platform.Status.PUBLICADO
    platform.validated_by = user
    platform.validated_at = now
    platform.updated_by = user
    platform.updated_at = now

    platform.save(
        update_fields=[
            "status",
            "validated_by",
            "validated_at",
            "updated_by",
            "updated_at",
        ]
    )

    return platform


@transaction.atomic
def mark_platform_obsolete(
    *,
    platform: models.Platform,
    user,
) -> models.Platform:
    """
    Marca como obsoleta una plataforma actualmente publicada.
    """

    platform = (
        models.Platform.all_objects
        .select_for_update()
        .get(pk=platform.pk)
    )

    validate_platform_for_obsolete(platform)

    now = timezone.now()

    platform.status = models.Platform.Status.OBSOLETO
    platform.updated_by = user
    platform.updated_at = now

    platform.save(
        update_fields=[
            "status",
            "updated_by",
            "updated_at",
        ]
    )

    return platform


@transaction.atomic
def reactivate_platform(
    *,
    platform: models.Platform,
    user,
) -> models.Platform:
    """
    Regresa una plataforma obsoleta a borrador para una nueva revisión.
    """

    platform = (
        models.Platform.all_objects
        .select_for_update()
        .get(pk=platform.pk)
    )

    validate_platform_for_reactivation(platform)

    now = timezone.now()

    platform.status = models.Platform.Status.BORRADOR

    platform.validated_by = None
    platform.validated_at = None

    platform.updated_by = user
    platform.updated_at = now

    platform.save(
        update_fields=[
            "status",
            "validated_by",
            "validated_at",
            "updated_by",
            "updated_at",
        ]
    )

    return platform


def check_platform_link(
    *,
    platform: models.Platform,
    user,
    url: str | None = None,
) -> models.LinkCheckLog:
    """
    Verifica la disponibilidad de la URL pública de una plataforma
    y registra el resultado en LinkCheckLog.

    ``base_api_url`` representa la API utilizada para cosecha y no
    se utiliza como URL pública. Si no se suministra ``url``, se utiliza
    la URL del último registro del historial.
    """

    platform_snapshot = (
        models.Platform.all_objects
        .get(pk=platform.pk)
    )

    if platform_snapshot.is_deleted:
        raise ValidationError({
            "detail": (
                "No se puede verificar el enlace de "
                "una plataforma eliminada."
            )
        })

    if url is None or not str(url).strip():
        latest_log = (
            models.LinkCheckLog.objects
            .filter(
                platform=platform_snapshot,
                journal_platform__isnull=True,
            )
            .order_by(*LINK_LOG_ORDERING)
            .first()
        )

        if latest_log is None:
            raise ValidationError({
                "url": (
                    "La plataforma no tiene una URL pública registrada "
                    "en el historial de verificación de enlaces."
                )
            })

        resolved_url: str = latest_log.url.strip()
    else:
        resolved_url = url.strip()

    _validate_safe_http_url(resolved_url)

    status_code, is_active = _perform_link_check(
        resolved_url
    )

    with transaction.atomic():
        current_platform = (
            models.Platform.all_objects
            .select_for_update()
            .get(pk=platform.pk)
        )

        if current_platform.is_deleted:
            raise ValidationError({
                "detail": (
                    "La plataforma fue eliminada durante "
                    "la verificación del enlace."
                )
            })

        fail_count = _get_next_fail_count(
            current_platform,
            url=resolved_url,
            is_active=is_active,
        )

        link_log = models.LinkCheckLog.objects.create(
            platform=current_platform,
            journal_platform=None,
            url=resolved_url,
            fail_count=fail_count,
            http_status_code=status_code,
            is_active=is_active,
            last_check=timezone.now(),
            created_by=user,
        )

    return link_log
