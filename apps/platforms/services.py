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
        "knowledge_areas",
        models.SharedPlatformKnowledgeArea,
        "knowledge_area",
        "un área del conocimiento activa asociada",
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
    (
        "academic_programs",
        models.SharedPlatformAcademicProgram,
        "academic_program",
        "un programa académico activo asociado",
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

    if not platform.base_api_url or not platform.base_api_url.strip():
        errors["base_api_url"] = (
            "La plataforma debe tener una URL antes de publicarse."
        )

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
            "base_api_url": (
                "La URL configurada no es válida."
            )
        })

    if parsed_url.scheme.lower() not in {"http", "https"}:
        raise ValidationError({
            "base_api_url": (
                "La URL debe utilizar el protocolo HTTP o HTTPS."
            )
        })

    hostname = parsed_url.hostname

    if not hostname:
        raise ValidationError({
            "base_api_url": (
                "La URL debe contener un nombre de host válido."
            )
        })

    if parsed_url.username or parsed_url.password:
        raise ValidationError({
            "base_api_url": (
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
            "base_api_url": (
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
                "base_api_url": (
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
                "base_api_url": (
                    "La URL resuelve a una dirección de red "
                    "privada, local o reservada."
                )
            })


def _get_next_fail_count(
    platform: models.Platform,
    *,
    is_active: bool,
) -> int:
    """
    Calcula la cantidad de fallos consecutivos del enlace.

    Una verificación exitosa reinicia el contador a cero.
    """

    if is_active:
        return 0

    latest_log = (
        models.LinkCheckLog.objects
        .filter(platform=platform)
        .order_by("-last_check", "-pk")
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

    # La validación anterior deja de ser vigente.
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
) -> models.LinkCheckLog:
    """
    Verifica la disponibilidad del enlace de una plataforma
    y registra el resultado en LinkCheckLog.

    El fail_count representa la cantidad de fallos consecutivos.
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

    if not platform_snapshot.base_api_url:
        raise ValidationError({
            "base_api_url": (
                "La plataforma no tiene una URL configurada."
            )
        })

    url = platform_snapshot.base_api_url.strip()

    _validate_safe_http_url(url)

    status_code, is_active = _perform_link_check(url)

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

        current_url = (
            current_platform.base_api_url or ""
        ).strip()

        if current_url != url:
            raise ValidationError({
                "base_api_url": (
                    "La URL de la plataforma cambió durante "
                    "la verificación. Debe realizarse nuevamente."
                )
            })

        fail_count = _get_next_fail_count(
            current_platform,
            is_active=is_active,
        )

        link_log = models.LinkCheckLog.objects.create(
            platform=current_platform,
            url=url,
            fail_count=fail_count,
            http_status_code=status_code,
            is_active=is_active,
            last_check=timezone.now(),
            created_by=user,
        )

    return link_log