from datetime import date

from django.test import TestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    KnowledgeArea,
    Language,
    MaterialType,
    SharedAcademicProgramKnowledgeArea,
)
from apps.journal import models, serializers
from apps.platforms.models import Platform


class JournalSerializersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )

        cls.editorial = Editorial.objects.create(
            name="Springer",
            created_by=cls.system,
        )

        cls.language = Language.objects.create(
            name="Español",
            abbreviation="es",
            created_by=cls.system,
        )

        cls.country = Country.objects.create(
            name="Colombia",
            abbreviation="co",
            emoji_flag="🇨🇴",
            created_by=cls.system,
        )

        cls.knowledge_area = KnowledgeArea.objects.create(
            name="Ingeniería",
            created_by=cls.system,
        )

        cls.material_type = MaterialType.objects.create(
            name="Artículos",
            created_by=cls.system,
        )

        cls.academic_program = AcademicProgram.objects.create(
            name="Ingeniería de Sistemas",
            created_by=cls.system,
        )

        cls.knowledge_area_secondary = KnowledgeArea.objects.create(
            name="Tecnología",
            created_by=cls.system,
        )

        cls.academic_program_secondary = AcademicProgram.objects.create(
            name="Ingeniería Electrónica",
            created_by=cls.system,
        )

        SharedAcademicProgramKnowledgeArea.objects.create(
            academic_program=cls.academic_program,
            knowledge_area=cls.knowledge_area,
            created_by=cls.system,
        )

        SharedAcademicProgramKnowledgeArea.objects.create(
            academic_program=cls.academic_program_secondary,
            knowledge_area=cls.knowledge_area,
            created_by=cls.system,
        )

        SharedAcademicProgramKnowledgeArea.objects.create(
            academic_program=cls.academic_program_secondary,
            knowledge_area=cls.knowledge_area_secondary,
            created_by=cls.system,
        )

        cls.platform = Platform.objects.create(
            name="Scopus Test",
            base_api_url="https://api.scopus.test",
            status=Platform.Status.PUBLICADO,
            created_by=cls.system,
        )

    def _journal(self, **kwargs):
        data = {
            "issn": "1234-5678",
            "title": "Journal de Prueba",
            "created_by": self.system,
        }

        data.update(kwargs)

        return models.Journal.objects.create(
            **data
        )

    # ==========================================================================
    # CREACIÓN Y NORMALIZACIÓN
    # ==========================================================================

    def test_journal_serializer_create_with_all_relations(self):
        """
        Crea una revista y sincroniza las seis relaciones configuradas.
        """
        data = {
            "issn": "1234 567X",
            "title": "Journal de Ingeniería",
            "editorial": self.editorial.pk,
            "license": "CC BY",
            "has_apc": False,
            "start_period": "2020-01-01",
            "languages": [self.language.pk],
            "countries": [self.country.pk],
            "material_types": [self.material_type.pk],
            "academic_programs": [
                self.academic_program.pk
            ],
            "platforms": [
                {
                    "platform": self.platform.pk,
                    "start_period": "2021-01-01",
                    "finish_period": "2026-12-31",
                    "has_full_text": True,
                }
            ],
        }

        serializer = serializers.JournalSerializer(
            data=data
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        journal = serializer.save(
            created_by=self.system
        )

        self.assertEqual(
            journal.issn,
            "1234-567X",
        )

        self.assertEqual(
            journal.language_links.count(),
            1,
        )

        self.assertEqual(
            journal.country_links.count(),
            1,
        )

        self.assertEqual(
            journal.knowledge_area_links.count(),
            1,
        )

        self.assertEqual(
            journal.material_type_links.count(),
            1,
        )

        self.assertEqual(
            journal.academic_program_links.count(),
            1,
        )

        self.assertEqual(
            journal.platform_links.count(),
            1,
        )

        platform_link = journal.platform_links.get(
            platform=self.platform
        )

        self.assertEqual(
            platform_link.start_period,
            date(2021, 1, 1),
        )

        self.assertEqual(
            platform_link.finish_period,
            date(2026, 12, 31),
        )

        self.assertTrue(
            platform_link.has_full_text
        )

    def test_journal_serializer_normalizes_issn(self):
        """
        Normaliza espacios, guion y mayúsculas del ISSN.
        """
        serializer = serializers.JournalSerializer(
            data={
                "issn": " 1234 567x ",
                "title": "ISSN Normalizado",
            }
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        self.assertEqual(
            serializer.validated_data["issn"],
            "1234-567X",
        )

    def test_journal_serializer_rejects_invalid_issn(self):
        """
        Rechaza ISSN con formato inválido.
        """
        serializer = serializers.JournalSerializer(
            data={
                "issn": "1234-56AB",
                "title": "ISSN Inválido",
            }
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "issn",
            serializer.errors,
        )

    # ==========================================================================
    # SINCRONIZACIÓN DE RELACIONES SIMPLES
    # ==========================================================================

    def test_sync_relations_deduplicates_repeated_ids(self):
        """
        IDs repetidos no generan relaciones duplicadas.
        """
        journal = self._journal(
            issn="2233-4455",
            title="Duplicates Test",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "academic_programs": [
                    self.academic_program.pk,
                    self.academic_program.pk,
                ],
                "languages": [
                    self.language.pk,
                    self.language.pk,
                ],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        self.assertEqual(
            models.SharedJournalKnowledgeArea.objects.filter(
                journal=journal
            ).count(),
            1,
        )

        self.assertEqual(
            models.SharedJournalLanguage.objects.filter(
                journal=journal
            ).count(),
            1,
        )

    def test_knowledge_areas_are_derived_from_academic_programs(self):
        serializer = serializers.JournalSerializer(
            data={
                "issn": "2345-6789",
                "title": "Journal Derivación",
                "academic_programs": [
                    self.academic_program.pk,
                    self.academic_program_secondary.pk,
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        journal = serializer.save(created_by=self.system)

        self.assertEqual(
            set(
                journal.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            {
                self.knowledge_area.pk,
                self.knowledge_area_secondary.pk,
            },
        )

    def test_knowledge_areas_are_not_writeable(self):
        serializer = serializers.JournalSerializer(
            data={
                "issn": "3456-7890",
                "title": "Journal Read Only",
                "knowledge_areas": [999999],
                "academic_programs": [self.academic_program.pk],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        journal = serializer.save(created_by=self.system)

        self.assertEqual(
            list(
                journal.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            [self.knowledge_area.pk],
        )

    def test_patch_without_academic_programs_preserves_derived_relations(self):
        journal = self._journal(
            issn="4567-8901",
            title="Journal Preserve",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={"academic_programs": [self.academic_program.pk]},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={"title": "Journal Preserve Updated"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        self.assertEqual(journal.academic_program_links.count(), 1)
        self.assertEqual(journal.knowledge_area_links.count(), 1)

    def test_empty_academic_programs_clears_derived_knowledge_areas(self):
        journal = self._journal(
            issn="5678-9012",
            title="Journal Clear",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={"academic_programs": [self.academic_program.pk]},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={"academic_programs": []},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        self.assertEqual(journal.academic_program_links.count(), 0)
        self.assertEqual(journal.knowledge_area_links.count(), 0)

    def test_changing_academic_programs_recalculates_knowledge_areas(self):
        journal = self._journal(
            issn="5789-0123",
            title="Journal Recalculate",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={"academic_programs": [self.academic_program.pk]},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "academic_programs": [
                    self.academic_program_secondary.pk,
                ]
            },
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        self.assertEqual(
            set(
                journal.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            {
                self.knowledge_area.pk,
                self.knowledge_area_secondary.pk,
            },
        )

    def test_removed_relations_are_soft_deleted_and_hidden(self):
        """
        Una lista vacía elimina lógicamente las relaciones y
        las excluye de la representación activa.
        """
        journal = self._journal(
            issn="5566-7788",
            title="Soft Delete Relations",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "languages": [
                    self.language.pk
                ],
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2020-01-01",
                        "finish_period": "2026-12-31",
                        "has_full_text": True,
                    }
                ],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        language_link = (
            journal.language_links.get(
                language=self.language
            )
        )

        platform_link = (
            journal.platform_links.get(
                platform=self.platform
            )
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "languages": [],
                "platforms": [],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        language_link.refresh_from_db()
        platform_link.refresh_from_db()

        self.assertTrue(
            language_link.is_deleted
        )

        self.assertTrue(
            platform_link.is_deleted
        )

        self.assertFalse(
            models.SharedJournalLanguage.objects.filter(
                pk=language_link.pk
            ).exists()
        )

        self.assertFalse(
            models.SharedJournalPlatform.objects.filter(
                pk=platform_link.pk
            ).exists()
        )

        self.assertTrue(
            models.SharedJournalLanguage.all_objects.filter(
                pk=language_link.pk
            ).exists()
        )

        self.assertTrue(
            models.SharedJournalPlatform.all_objects.filter(
                pk=platform_link.pk
            ).exists()
        )

        representation = serializers.JournalSerializer(
            instance=journal
        ).data

        self.assertEqual(
            representation["languages"],
            [],
        )

        self.assertEqual(
            representation["platforms"],
            [],
        )

    def test_archived_relation_is_restored(self):
        """
        Una relación simple previamente eliminada se restaura.
        """
        journal = self._journal(
            issn="6677-8899",
            title="Restore Relation",
        )

        link = (
            models.SharedJournalLanguage.objects.create(
                journal=journal,
                language=self.language,
                created_by=self.system,
            )
        )

        link.soft_delete(
            user=self.system,
            explanation="Eliminada para prueba",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "languages": [
                    self.language.pk
                ],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        link.refresh_from_db()

        self.assertFalse(
            link.is_deleted
        )

        self.assertTrue(
            models.SharedJournalLanguage.objects.filter(
                pk=link.pk
            ).exists()
        )

    # ==========================================================================
    # RELACIÓN ENRIQUECIDA JOURNAL <-> PLATFORM
    # ==========================================================================

    def test_platform_relation_updates_extra_fields(self):
        """
        Actualiza los atributos propios de SharedJournalPlatform.
        """
        journal = self._journal(
            issn="3344-5566",
            title="Platform Update Test",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2020-01-01",
                        "finish_period": "2025-12-31",
                        "has_full_text": False,
                    }
                ]
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2021-01-01",
                        "has_full_text": True,
                    }
                ]
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        link = journal.platform_links.get(
            platform=self.platform
        )

        self.assertEqual(
            link.start_period,
            date(2021, 1, 1),
        )

        self.assertEqual(
            link.finish_period,
            date(2025, 12, 31),
        )

        self.assertTrue(
            link.has_full_text
        )

    def test_platform_relation_rejects_invalid_period(self):
        """
        Rechaza una cobertura de plataforma con período invertido.
        """
        serializer = serializers.JournalSerializer(
            data={
                "issn": "4455-6677",
                "title": "Invalid Platform Period",
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2026-01-01",
                        "finish_period": "2025-01-01",
                    }
                ],
            }
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "platforms",
            serializer.errors,
        )

    def test_archived_platform_relation_is_restored_and_updated(self):
        """
        Una relación plataforma archivada se restaura y actualiza
        mediante el mecanismo genérico de relaciones enriquecidas.
        """
        journal = self._journal(
            issn="7788-9900",
            title="Restore Platform Relation",
        )

        link = (
            models.SharedJournalPlatform.objects.create(
                journal=journal,
                platform=self.platform,
                start_period=date(2020, 1, 1),
                finish_period=date(2024, 12, 31),
                has_full_text=False,
                created_by=self.system,
            )
        )

        link.soft_delete(
            user=self.system,
            explanation="Eliminada para prueba",
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2021-01-01",
                        "finish_period": "2026-12-31",
                        "has_full_text": True,
                    }
                ]
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        link.refresh_from_db()

        self.assertFalse(
            link.is_deleted
        )

        self.assertEqual(
            link.start_period,
            date(2021, 1, 1),
        )

        self.assertEqual(
            link.finish_period,
            date(2026, 12, 31),
        )

        self.assertTrue(
            link.has_full_text
        )

    def test_duplicate_platforms_are_rejected(self):
        """
        La misma plataforma no puede aparecer dos veces
        en la misma petición.
        """
        serializer = serializers.JournalSerializer(
            data={
                "issn": "1010-2233",
                "title": "Duplicate Platforms",
                "platforms": [
                    {
                        "platform": self.platform.pk,
                        "start_period": "2020-01-01",
                    },
                    {
                        "platform": self.platform.pk,
                        "start_period": "2021-01-01",
                    },
                ],
            }
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "platforms",
            serializer.errors,
        )

    def test_platform_relation_rejects_draft_platform(self):
        draft_platform = Platform.objects.create(
            name="Draft Association",
            status=Platform.Status.BORRADOR,
            created_by=self.system,
        )

        serializer = serializers.JournalSerializer(
            data={
                "issn": "6789-0123",
                "title": "Draft Association Journal",
                "platforms": [{"platform": draft_platform.pk}],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("platforms", serializer.errors)

    def test_platform_relation_rejects_obsolete_platform(self):
        obsolete_platform = Platform.objects.create(
            name="Obsolete Association",
            status=Platform.Status.OBSOLETO,
            created_by=self.system,
        )

        serializer = serializers.JournalSerializer(
            data={
                "issn": "7890-1234",
                "title": "Obsolete Association Journal",
                "platforms": [{"platform": obsolete_platform.pk}],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("platforms", serializer.errors)

    def test_platform_relation_allows_published_platform(self):
        serializer = serializers.JournalSerializer(
            data={
                "issn": "8901-2345",
                "title": "Published Association Journal",
                "platforms": [{"platform": self.platform.pk}],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    # ==========================================================================
    # RESTAURACIÓN DE JOURNAL
    # ==========================================================================

    def test_archived_journal_restored_via_serializer(self):
        """
        Una revista archivada con el mismo ISSN se restaura.
        """
        journal = self._journal(
            issn="8899-0011",
            title="Revista Archivada",
        )

        journal.soft_delete(
            user=self.system,
            explanation="Archivada para prueba",
        )

        serializer = serializers.JournalSerializer(
            data={
                "issn": "8899 0011",
                "title": "Revista Restaurada",
            }
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        restored = serializer.save(
            created_by=self.system
        )

        self.assertEqual(
            restored.pk,
            journal.pk,
        )

        self.assertFalse(
            restored.is_deleted
        )

        self.assertEqual(
            restored.issn,
            "8899-0011",
        )

        self.assertEqual(
            restored.title,
            "Revista Restaurada",
        )

    def test_partial_update_without_relations_keeps_existing_relations(self):
        """
        Un PATCH que no envía relaciones no debe modificarlas.
        """
        journal = self._journal(
            issn="9900-1122",
            title="Partial Update",
        )

        models.SharedJournalLanguage.objects.create(
            journal=journal,
            language=self.language,
            created_by=self.system,
        )

        serializer = serializers.JournalSerializer(
            instance=journal,
            data={
                "title": "Título Actualizado",
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system
        )

        journal.refresh_from_db()

        self.assertEqual(
            journal.language_links.count(),
            1,
        )

        self.assertEqual(
            journal.title,
            "Título Actualizado",
        )

    # ==========================================================================
    # SERIALIZER PÚBLICO
    # ==========================================================================

    def test_public_serializer_excludes_audit_fields_and_includes_public_platform(self):
        """
        El serializer público oculta auditoría y representa
        únicamente plataformas publicadas.
        """
        journal = self._journal(
            issn="1122-3344",
            title="Public Journal",
        )

        models.SharedJournalKnowledgeArea.objects.create(
            journal=journal,
            knowledge_area=self.knowledge_area,
            created_by=self.system,
        )

        models.SharedJournalPlatform.objects.create(
            journal=journal,
            platform=self.platform,
            start_period=date(2020, 1, 1),
            finish_period=date(2026, 12, 31),
            has_full_text=True,
            created_by=self.system,
        )

        draft_platform = Platform.objects.create(
            name="Draft Platform",
            base_api_url="https://api.draft.test",
            status=Platform.Status.BORRADOR,
            created_by=self.system,
        )

        models.SharedJournalPlatform.objects.create(
            journal=journal,
            platform=draft_platform,
            created_by=self.system,
        )

        data = serializers.JournalPublicSerializer(
            journal
        ).data

        self.assertNotIn(
            "created_by",
            data,
        )

        self.assertNotIn(
            "updated_by",
            data,
        )

        self.assertNotIn(
            "deleted_by",
            data,
        )

        self.assertNotIn(
            "delete_explanation",
            data,
        )

        self.assertEqual(
            data["issn"],
            "1122-3344",
        )

        self.assertEqual(
            data["knowledge_areas"],
            [
                {
                    "id": self.knowledge_area.pk,
                    "name": self.knowledge_area.name,
                }
            ],
        )

        self.assertEqual(
            len(data["platforms"]),
            1,
        )

        self.assertEqual(
            data["platforms"][0],
            {
                "id": self.platform.pk,
                "name": self.platform.name,
                "base_api_url": self.platform.base_api_url,
                "start_period": date(2020, 1, 1),
                "finish_period": date(2026, 12, 31),
                "has_full_text": True,
            },
        )