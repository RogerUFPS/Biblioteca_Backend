"""Clasificación derivada perteneciente al dominio Journal."""

from collections import defaultdict
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import SharedAcademicProgramKnowledgeArea
from apps.core.relations import sync_auditable_relation_ids

from . import models


JOURNAL_DERIVED_DELETE = (
    "Área derivada retirada al recalcular la clasificación de la revista."
)


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


def related_platform_ids(journal_ids: Iterable[int]) -> set[int]:
    """Obtiene Platforms vinculadas sin conocer cómo se clasifican."""
    return set(
        models.SharedJournalPlatform.objects.filter(
            journal_id__in=set(journal_ids),
        ).values_list("platform_id", flat=True)
    )


@transaction.atomic
def recalculate_journals(
    journal_ids: Iterable[int],
    *,
    user,
    invalidate_on_change: bool = True,
) -> set[int]:
    """Materializa áreas y devuelve únicamente IDs de Journals cambiadas."""
    ids = set(journal_ids)
    if not ids:
        return set()

    program_ids_by_journal: dict[int, set[int]] = defaultdict(set)
    all_program_ids: set[int] = set()
    rows = models.SharedJournalAcademicProgram.objects.filter(
        journal_id__in=ids,
        journal__deleted_at__isnull=True,
        academic_program__deleted_at__isnull=True,
    ).values_list("journal_id", "academic_program_id")
    for journal_id, program_id in rows:
        program_ids_by_journal[journal_id].add(program_id)
        all_program_ids.add(program_id)

    areas_by_program = _area_ids_by_program(all_program_ids)
    area_links_by_journal: dict[int, list] = defaultdict(list)
    for link in models.SharedJournalKnowledgeArea.all_objects.filter(
        journal_id__in=ids
    ):
        area_links_by_journal[link.journal_id].append(link)

    changed_journal_ids: set[int] = set()
    journals = models.Journal.all_objects.select_for_update().filter(pk__in=ids)
    for journal in journals:
        program_ids = program_ids_by_journal.get(journal.pk, set())
        desired = (
            set().union(*(areas_by_program.get(pk, set()) for pk in program_ids))
            if program_ids else set()
        )
        changed = sync_auditable_relation_ids(
            through_model=models.SharedJournalKnowledgeArea,
            parent_field="journal",
            parent_id=journal.pk,
            related_field="knowledge_area",
            desired_ids=desired,
            user=user,
            delete_explanation=JOURNAL_DERIVED_DELETE,
            existing_links=area_links_by_journal.get(journal.pk, []),
        )
        if not changed:
            continue
        changed_journal_ids.add(journal.pk)
        if invalidate_on_change and (journal.active or journal.validated_at is not None):
            now = timezone.now()
            journal.active = False
            journal.validated_by = None
            journal.validated_at = None
            journal.updated_by = user
            journal.updated_at = now
            journal.save(update_fields=[
                "active", "validated_by", "validated_at", "updated_by", "updated_at",
            ])
    return changed_journal_ids


def propagate_catalog_change(program_ids: Iterable[int], *, user) -> set[int]:
    """Coordina Journal→Platform después de un cambio efectivo de catálogo."""
    ids = set(program_ids)
    journal_ids = set(
        models.SharedJournalAcademicProgram.objects.filter(
            academic_program_id__in=ids,
            journal__deleted_at__isnull=True,
        ).values_list("journal_id", flat=True)
    )
    changed_journal_ids = recalculate_journals(
        journal_ids, user=user, invalidate_on_change=True
    )
    platform_ids = related_platform_ids(changed_journal_ids)
    if platform_ids:
        from apps.platforms.classification import recalculate_platforms
        recalculate_platforms(platform_ids, user=user)
    return platform_ids

