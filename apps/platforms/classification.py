"""Clasificación derivada perteneciente al dominio Platform."""

from collections import defaultdict
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import SharedAcademicProgramKnowledgeArea
from apps.core.relations import sync_auditable_relation_ids
from apps.journal import models as journal_models

from . import models


PROGRAM_DELETE = "Programa derivado retirado al recalcular la plataforma."
AREA_DELETE = "Área derivada retirada al recalcular la plataforma."


def _area_ids_by_program(program_ids: set[int]) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    rows = SharedAcademicProgramKnowledgeArea.objects.filter(
        academic_program_id__in=program_ids,
        academic_program__deleted_at__isnull=True,
        knowledge_area__deleted_at__isnull=True,
    ).values_list("academic_program_id", "knowledge_area_id")
    for program_id, area_id in rows:
        result[program_id].add(area_id)
    return result


@transaction.atomic
def recalculate_platforms(platform_ids: Iterable[int], *, user) -> set[int]:
    """Materializa programas y áreas desde las Journals elegibles."""
    ids = set(platform_ids)
    if not ids:
        return set()

    programs_by_platform: dict[int, set[int]] = defaultdict(set)
    eligible_journals: dict[int, set[int]] = defaultdict(set)
    rows = journal_models.SharedJournalPlatform.objects.filter(
        platform_id__in=ids,
        journal__deleted_at__isnull=True,
        journal__active=True,
        journal__validated_at__isnull=False,
        journal__academic_program_links__deleted_at__isnull=True,
        journal__academic_program_links__academic_program_id__isnull=False,
        journal__academic_program_links__academic_program__deleted_at__isnull=True,
    ).values_list(
        "platform_id", "journal_id",
        "journal__academic_program_links__academic_program_id",
    )
    for platform_id, journal_id, program_id in rows:
        eligible_journals[platform_id].add(journal_id)
        if program_id is not None:
            programs_by_platform[platform_id].add(program_id)

    eligible_rows = journal_models.SharedJournalPlatform.objects.filter(
        platform_id__in=ids,
        journal__deleted_at__isnull=True,
        journal__active=True,
        journal__validated_at__isnull=False,
    ).values_list("platform_id", "journal_id")
    for platform_id, journal_id in eligible_rows:
        eligible_journals[platform_id].add(journal_id)

    all_program_ids = (
        set().union(*programs_by_platform.values()) if programs_by_platform else set()
    )
    areas_by_program = _area_ids_by_program(all_program_ids)
    program_links: dict[int, list] = defaultdict(list)
    for link in models.SharedPlatformAcademicProgram.all_objects.filter(
        platform_id__in=ids
    ):
        program_links[link.platform_id].append(link)
    area_links: dict[int, list] = defaultdict(list)
    for link in models.SharedPlatformKnowledgeArea.all_objects.filter(
        platform_id__in=ids
    ):
        area_links[link.platform_id].append(link)

    changed_platform_ids: set[int] = set()
    platforms = models.Platform.all_objects.select_for_update().filter(pk__in=ids)
    for platform in platforms:
        desired_programs = programs_by_platform.get(platform.pk, set())
        desired_areas = (
            set().union(*(
                areas_by_program.get(program_id, set())
                for program_id in desired_programs
            )) if desired_programs else set()
        )
        programs_changed = sync_auditable_relation_ids(
            through_model=models.SharedPlatformAcademicProgram,
            parent_field="platform", parent_id=platform.pk,
            related_field="academic_program", desired_ids=desired_programs,
            user=user, delete_explanation=PROGRAM_DELETE,
            existing_links=program_links.get(platform.pk, []),
        )
        areas_changed = sync_auditable_relation_ids(
            through_model=models.SharedPlatformKnowledgeArea,
            parent_field="platform", parent_id=platform.pk,
            related_field="knowledge_area", desired_ids=desired_areas,
            user=user, delete_explanation=AREA_DELETE,
            existing_links=area_links.get(platform.pk, []),
        )
        if programs_changed or areas_changed:
            changed_platform_ids.add(platform.pk)
        if (
            eligible_journals.get(platform.pk)
            and (not desired_programs or not desired_areas)
            and platform.status == models.Platform.Status.PUBLICADO
        ):
            now = timezone.now()
            platform.status = models.Platform.Status.BORRADOR
            platform.validated_by = None
            platform.validated_at = None
            platform.updated_by = user
            platform.updated_at = now
            platform.save(update_fields=[
                "status", "validated_by", "validated_at", "updated_by", "updated_at",
            ])
            changed_platform_ids.add(platform.pk)
    return changed_platform_ids
