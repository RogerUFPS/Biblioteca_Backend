from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    Language,
    MaterialType,
    SharedAcademicProgramKnowledgeArea,
)
from apps.platforms.models import Platform

from . import models
from .classification import (
    recalculate_journals,
    related_platform_ids,
)
from apps.platforms.classification import recalculate_platforms


JOURNAL_RELATION_CONFIG = (
    # (
    #     input_field,
    #     through_model,
    #     relation_field,
    #     target_model,
    # )
    (
        "language_ids",
        models.SharedJournalLanguage,
        "language",
        Language,
    ),
    (
        "country_ids",
        models.SharedJournalCountry,
        "country",
        Country,
    ),
    (
        "material_type_ids",
        models.SharedJournalMaterialType,
        "material_type",
        MaterialType,
    ),
    (
        "academic_program_ids",
        models.SharedJournalAcademicProgram,
        "academic_program",
        AcademicProgram,
    ),
)


def validate_platform_for_journal_association(
    platform: Platform,
    *,
    field_name: str = "platform_id",
) -> None:
    """
    Garantiza que una revista solo pueda asociarse a una plataforma
    publicada.

    Esta validación se reutiliza tanto en el serializer administrativo
    como en el servicio interno de creación/cosecha.
    """
    if platform.status != Platform.Status.PUBLICADO:
        raise ValidationError(
            {
                field_name: (
                    "La revista no puede asociarse a una plataforma "
                    "que no esté publicada."
                )
            }
        )


<<<<<<< HEAD
def _get_knowledge_area_ids_from_academic_programs(
    academic_program_ids: list[int],
) -> list[int]:
    """
    Obtiene la unión sin duplicados de áreas del conocimiento asociadas
    a los programas académicos suministrados, respetando Soft Delete.
    """
    unique_program_ids = set(academic_program_ids)

    if not unique_program_ids:
        return []

    existing_program_ids = set(
        AcademicProgram.objects
        .filter(pk__in=unique_program_ids)
        .values_list("pk", flat=True)
    )

    missing_ids = unique_program_ids - existing_program_ids

    if missing_ids:
        raise ValidationError(
            {
                "academic_program_ids": (
                    "Los siguientes IDs no existen o se encuentran eliminados: "
                    f"{sorted(missing_ids)}."
                )
            }
        )

    return list(
        SharedAcademicProgramKnowledgeArea.objects.filter(
            academic_program_id__in=unique_program_ids,
            deleted_at__isnull=True,
            knowledge_area__deleted_at__isnull=True,
        )
        .values_list("knowledge_area_id", flat=True)
        .distinct()
    )


=======
>>>>>>> production
def _normalize_issn(issn: str) -> str:
    """
    Normaliza el ISSN al formato XXXX-XXXX.

    Se admite como entrada con o sin guion y se normaliza
    la letra de control X a mayúscula.
    """

    if not issn or not issn.strip():
        raise ValidationError(
            {
                "issn": "El ISSN es obligatorio."
            }
        )

    compact_issn = (
        "".join(issn.split())
        .replace("-", "")
        .upper()
    )

    if (
        len(compact_issn) != 8
        or not compact_issn[:7].isdigit()
        or not (
            compact_issn[7].isdigit()
            or compact_issn[7] == "X"
        )
    ):
        raise ValidationError(
            {
                "issn": (
                    "El ISSN debe tener el formato XXXX-XXXX."
                )
            }
        )

    return (
        f"{compact_issn[:4]}-"
        f"{compact_issn[4:]}"
    )


def _validate_period(
    start_period: date | None,
    finish_period: date | None,
    *,
    finish_field: str = "finish_period",
) -> None:
    """
    Verifica que el período final no sea anterior
    al período inicial.
    """

    if (
        start_period
        and finish_period
        and finish_period < start_period
    ):
        raise ValidationError(
            {
                finish_field: (
                    "El período final no puede ser anterior "
                    "al período inicial."
                )
            }
        )


def _validate_editorial(
    editorial_id: int | None,
) -> None:
    """
    Verifica que la editorial exista y se encuentre activa.
    """

    if editorial_id is None:
        return

    if not Editorial.objects.filter(
        pk=editorial_id
    ).exists():
        raise ValidationError(
            {
                "editorial_id": (
                    "La editorial indicada no existe "
                    "o se encuentra eliminada."
                )
            }
        )


def _sync_relation_ids(
    *,
    journal: models.Journal,
    ids: list[int],
    through_model,
    relation_field: str,
    target_model,
    input_field: str,
    user,
) -> None:
    """
    Sincroniza una relación simple de Journal mediante IDs.

    Permite:
    - eliminar relaciones mediante Soft Delete;
    - restaurar relaciones archivadas;
    - crear relaciones nuevas;
    - evitar IDs duplicados;
    - rechazar registros inexistentes o eliminados.
    """

    unique_ids = set(ids)

    existing_target_ids = set(
        target_model.objects
        .filter(
            pk__in=unique_ids
        )
        .values_list(
            "pk",
            flat=True,
        )
    )

    missing_ids = (
        unique_ids
        - existing_target_ids
    )

    if missing_ids:
        raise ValidationError(
            {
                input_field: (
                    "Los siguientes IDs no existen "
                    "o se encuentran eliminados: "
                    f"{sorted(missing_ids)}."
                )
            }
        )

    current_links = through_model.objects.filter(
        journal=journal
    )

    current_ids = set(
        current_links.values_list(
            f"{relation_field}_id",
            flat=True,
        )
    )

    ids_to_remove = (
        current_ids
        - unique_ids
    )

    ids_to_add = (
        unique_ids
        - current_ids
    )

    if ids_to_remove:
        links_to_remove = current_links.filter(
            **{
                f"{relation_field}_id__in": ids_to_remove,
            }
        )

        for link in links_to_remove:
            link.soft_delete(
                user=user,
                explanation=(
                    "Relación eliminada durante "
                    "la actualización de la revista."
                ),
            )

    for related_id in ids_to_add:
        lookup = {
            "journal": journal,
            f"{relation_field}_id": related_id,
        }

        archived_link = (
            through_model.all_objects
            .filter(
                deleted_at__isnull=False,
                **lookup,
            )
            .first()
        )

        if archived_link:
            archived_link.restore()

            archived_link.updated_by = user
            archived_link.updated_at = timezone.now()

            archived_link.save(
                update_fields=[
                    "updated_by",
                    "updated_at",
                ]
            )

        else:
            through_model.objects.create(
                journal=journal,
                **{
                    f"{relation_field}_id": related_id,
                },
                created_by=user,
            )


def _sync_source_platform(
    *,
    journal: models.Journal,
    platform_id: int,
    start_period: date | None,
    finish_period: date | None,
    has_full_text: bool | None,
    user,
) -> None:
    """
    Crea, actualiza o restaura la relación entre una revista
    y la plataforma desde la cual fue obtenida.

    Esta relación se maneja separadamente porque contiene
    atributos propios de cobertura.
    """

    platform = (
        Platform.objects
        .filter(
            pk=platform_id
        )
        .first()
    )

    if platform is None:
        raise ValidationError(
            {
                "platform_id": (
                    "La plataforma indicada no existe "
                    "o se encuentra eliminada."
                )
            }
        )

    validate_platform_for_journal_association(
        platform,
        field_name="platform_id",
    )

    active_link = (
        models.SharedJournalPlatform.objects
        .filter(
            journal=journal,
            platform=platform,
        )
        .first()
    )

    if active_link:
        effective_start = (
            start_period
            if start_period is not None
            else active_link.start_period
        )

        effective_finish = (
            finish_period
            if finish_period is not None
            else active_link.finish_period
        )

        _validate_period(
            effective_start,
            effective_finish,
            finish_field="platform_finish_period",
        )

        update_fields = []

        if start_period is not None:
            active_link.start_period = start_period
            update_fields.append(
                "start_period"
            )

        if finish_period is not None:
            active_link.finish_period = finish_period
            update_fields.append(
                "finish_period"
            )

        if has_full_text is not None:
            active_link.has_full_text = has_full_text
            update_fields.append(
                "has_full_text"
            )

        active_link.updated_by = user
        active_link.updated_at = timezone.now()

        update_fields.extend(
            [
                "updated_by",
                "updated_at",
            ]
        )

        active_link.save(
            update_fields=update_fields
        )

        return

    validate_platform_for_journal_association(
        platform,
        field_name="platform_id",
    )

    archived_link = (
        models.SharedJournalPlatform.all_objects
        .filter(
            journal=journal,
            platform=platform,
            deleted_at__isnull=False,
        )
        .first()
    )

    if archived_link:
        effective_start = (
            start_period
            if start_period is not None
            else archived_link.start_period
        )

        effective_finish = (
            finish_period
            if finish_period is not None
            else archived_link.finish_period
        )

        _validate_period(
            effective_start,
            effective_finish,
            finish_field="platform_finish_period",
        )

        archived_link.restore()

        if start_period is not None:
            archived_link.start_period = start_period

        if finish_period is not None:
            archived_link.finish_period = finish_period

        if has_full_text is not None:
            archived_link.has_full_text = has_full_text

        archived_link.updated_by = user
        archived_link.updated_at = timezone.now()

        archived_link.save(
            update_fields=[
                "start_period",
                "finish_period",
                "has_full_text",
                "updated_by",
                "updated_at",
            ]
        )

        return

    _validate_period(
        start_period,
        finish_period,
        finish_field="platform_finish_period",
    )

    models.SharedJournalPlatform.objects.create(
        journal=journal,
        platform=platform,
        start_period=start_period,
        finish_period=finish_period,
        has_full_text=(
            has_full_text
            if has_full_text is not None
            else False
        ),
        created_by=user,
    )


@transaction.atomic
def create_journal(
    *,
    issn: str,
    title: str,
    user,
    editorial_id: int | None = None,
    license: str | None = None,
    url_image: str | None = None,
    has_apc: bool | None = None,
    active: bool | None = None,
    start_period: date | None = None,
    finish_period: date | None = None,
    language_ids: list[int] | None = None,
    country_ids: list[int] | None = None,
    material_type_ids: list[int] | None = None,
    academic_program_ids: list[int] | None = None,
    platform_id: int | None = None,
    platform_start_period: date | None = None,
    platform_finish_period: date | None = None,
    has_full_text: bool | None = None,
) -> models.Journal:
    """
    Crea o actualiza una revista utilizando el ISSN como
    identificador principal.

    Comportamiento:

    - Si el ISSN no existe, crea una revista.
    - Si el ISSN ya existe, actualiza esa revista.
    - Si la revista con ese ISSN estaba eliminada, la restaura.
    - Sincroniza únicamente las clasificaciones suministradas.
    - Registra la plataforma de procedencia cuando se proporciona.
    - Actualiza fetched_at cuando proviene de una plataforma.

    None en una colección significa "no modificar".
    Una lista vacía significa "eliminar todas las relaciones".

    Las áreas del conocimiento no se reciben como entrada: se derivan
    exclusivamente de ``academic_program_ids``.

    Este servicio está diseñado como punto de entrada interno para
    los procesos de cosecha y otros procesos backend.
    """

    normalized_issn = _normalize_issn(
        issn
    )

    normalized_title = (
        title.strip()
        if title
        else ""
    )

    if not normalized_title:
        raise ValidationError(
            {
                "title": (
                    "El título de la revista es obligatorio."
                )
            }
        )

    _validate_editorial(
        editorial_id
    )

    now = timezone.now()

    created = False

    journal = (
        models.Journal.all_objects
        .select_for_update()
        .filter(
            issn__iexact=normalized_issn
        )
        .first()
    )

    if journal is None:
        _validate_period(
            start_period,
            finish_period,
        )

        create_data = {
            "issn": normalized_issn,
            "title": normalized_title,
            "created_by": user,
        }

        if editorial_id is not None:
            create_data["editorial_id"] = editorial_id

        if license is not None:
            create_data["license"] = license

        if url_image is not None:
            create_data["url_image"] = url_image

        if has_apc is not None:
            create_data["has_apc"] = has_apc

        if active is not None:
            create_data["active"] = active

        if start_period is not None:
            create_data["start_period"] = start_period

        if finish_period is not None:
            create_data["finish_period"] = finish_period

        if platform_id is not None:
            create_data["fetched_at"] = now

        try:
            # El bloque interno crea un savepoint.
            # Si otro proceso creó simultáneamente el mismo ISSN,
            # solo se revierte este intento de INSERT.
            with transaction.atomic():
                journal = models.Journal.objects.create(
                    **create_data
                )

            created = True

        except IntegrityError:
            journal = (
                models.Journal.all_objects
                .select_for_update()
                .filter(
                    issn__iexact=normalized_issn
                )
                .first()
            )

            if journal is None:
                raise

    if not created:
        was_deleted = journal.is_deleted

        if was_deleted:
            journal.restore()

        effective_start = (
            start_period
            if start_period is not None
            else journal.start_period
        )

        effective_finish = (
            finish_period
            if finish_period is not None
            else journal.finish_period
        )

        _validate_period(
            effective_start,
            effective_finish,
        )

        update_fields = []

        if journal.issn != normalized_issn:
            journal.issn = normalized_issn
            update_fields.append(
                "issn"
            )

        if journal.title != normalized_title:
            journal.title = normalized_title
            update_fields.append(
                "title"
            )

        if editorial_id is not None:
            journal.editorial_id = editorial_id
            update_fields.append(
                "editorial_id"
            )

        if license is not None:
            journal.license = license
            update_fields.append(
                "license"
            )

        if url_image is not None:
            journal.url_image = url_image
            update_fields.append(
                "url_image"
            )

        if has_apc is not None:
            journal.has_apc = has_apc
            update_fields.append(
                "has_apc"
            )

        if active is not None:
            journal.active = active
            update_fields.append(
                "active"
            )

        if start_period is not None:
            journal.start_period = start_period
            update_fields.append(
                "start_period"
            )

        if finish_period is not None:
            journal.finish_period = finish_period
            update_fields.append(
                "finish_period"
            )

        if platform_id is not None:
            journal.fetched_at = now
            update_fields.append(
                "fetched_at"
            )

        if was_deleted:
            journal.active = False
            # Una revista restaurada requiere una nueva validación.
            journal.validated_by = None
            journal.validated_at = None

            update_fields.extend(
                [
                    "active",
                    "validated_by",
                    "validated_at",
                ]
            )

        journal.updated_by = user
        journal.updated_at = now

        update_fields.extend(
            [
                "updated_by",
                "updated_at",
            ]
        )

        journal.save(
            update_fields=list(
                dict.fromkeys(
                    update_fields
                )
            )
        )

    relation_values = {
        "language_ids": language_ids,
        "country_ids": country_ids,
        "material_type_ids": material_type_ids,
        "academic_program_ids": academic_program_ids,
    }

    for (
        input_field,
        through_model,
        relation_field,
        target_model,
    ) in JOURNAL_RELATION_CONFIG:

        relation_ids = relation_values[
            input_field
        ]

        if relation_ids is None:
            continue

        _sync_relation_ids(
            journal=journal,
            ids=relation_ids,
            through_model=through_model,
            relation_field=relation_field,
            target_model=target_model,
            input_field=input_field,
            user=user,
        )

    if academic_program_ids is not None:
        derived_knowledge_area_ids = (
            _get_knowledge_area_ids_from_academic_programs(
                academic_program_ids
            )
        )

        _sync_relation_ids(
            journal=journal,
            ids=derived_knowledge_area_ids,
            through_model=models.SharedJournalKnowledgeArea,
            relation_field="knowledge_area",
            target_model=KnowledgeArea,
            input_field="knowledge_area_ids",
            user=user,
        )

    if platform_id is not None:
        _sync_source_platform(
            journal=journal,
            platform_id=platform_id,
            start_period=platform_start_period,
            finish_period=platform_finish_period,
            has_full_text=has_full_text,
            user=user,
        )

    recalculate_journals(
        [journal.pk],
        user=user,
        invalidate_on_change=False,
    )

    if not created and (journal.active or journal.validated_at is not None):
        journal.active = False
        journal.validated_by = None
        journal.validated_at = None
        journal.updated_by = user
        journal.updated_at = now
        journal.save(update_fields=[
            "active", "validated_by", "validated_at", "updated_by", "updated_at",
        ])

    recalculate_platforms(related_platform_ids([journal.pk]), user=user)

    return journal
