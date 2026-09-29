from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import models


REQUIRED_PLATFORM_RELATIONS = (
    (
        "institutions",
        models.SharedPlatformSupport,
        "institution",
        "institución responsable",
    ),
    (
        "countries",
        models.SharedPlatformCountry,
        "country",
        "país",
    ),
    (
        "knowledge_areas",
        models.SharedPlatformKnowledgeArea,
        "knowledge_area",
        "área del conocimiento",
    ),
    (
        "material_types",
        models.SharedPlatformMaterialType,
        "material_type",
        "tipo de material",
    ),
    (
        "languages",
        models.SharedPlatformLanguage,
        "language",
        "idioma",
    ),
    (
        "academic_programs",
        models.SharedPlatformAcademicProgram,
        "academic_program",
        "programa académico",
    ),
)


def validate_platform_for_publication(platform: models.Platform) -> None:
    """
    Valida que la plataforma pueda pasar de borrador a publicado.
    """

    errors = {}

    if platform.is_deleted:
        errors["detail"] = (
            "No se puede publicar una plataforma que se encuentra eliminada."
        )

    if platform.status == models.Platform.Status.PUBLICADO:
        errors["status"] = "La plataforma ya se encuentra publicada."

    elif platform.status == models.Platform.Status.OBSOLETO:
        errors["status"] = (
            "Una plataforma obsoleta debe regresar primero a borrador "
            "antes de volver a publicarse."
        )

    if not platform.name or not platform.name.strip():
        errors["name"] = "La plataforma debe tener un nombre."

    if not platform.base_api_url:
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
        pk=platform.valid_sintaxis_id
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
                f"La plataforma debe tener al menos un {label} activo asociado."
            )

    if errors:
        raise ValidationError(errors)


def validate_platform_for_obsolete(platform: models.Platform) -> None:
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


def validate_platform_for_reactivation(platform: models.Platform) -> None:
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