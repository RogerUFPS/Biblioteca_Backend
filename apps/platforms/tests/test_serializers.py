from django.test import TestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
    SharedAcademicProgramKnowledgeArea,
)
from apps.platforms import models, serializers


class PlatformSerializersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )

        cls.institution = Institution.objects.create(
            name="UFPS",
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

        cls.knowledge_area_secondary = KnowledgeArea.objects.create(
            name="Ciencias de la Computación",
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

        cls.academic_program_secondary = AcademicProgram.objects.create(
            name="Ingeniería Civil",
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

        cls.sintaxis = models.ValidSintaxis.objects.create(
            name="Sintaxis Estandar",
            booleans=["AND", "OR"],
            parenthesis=True,
            fields={"title": "ti"},
            created_by=cls.system,
        )

    def test_platform_serializer_create_with_api_key_and_relations(self):
        """Persiste la API Key cifrada y sincroniza relaciones."""
        data = {
            "name": "Redalyc",
            "base_api_url": "https://www.redalyc.org",
            "api_key": "my-plain-text-key",
            "start_period": "2000-01-01",
            "valid_sintaxis": self.sintaxis.pk,
            "institutions": [self.institution.pk],
            "languages": [self.language.pk],
            "countries": [self.country.pk],
            "material_types": [self.material_type.pk],
            "academic_programs": [self.academic_program.pk],
        }

        serializer = serializers.PlatformSerializer(data=data)

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        platform = serializer.save(
            created_by=self.system,
        )

        self.assertEqual(
            platform.status,
            models.Platform.Status.BORRADOR,
        )

        self.assertEqual(
            platform.get_api_key(),
            "my-plain-text-key",
        )

        self.assertEqual(
            platform.support_links.count(),
            1,
        )

        self.assertEqual(
            platform.country_links.count(),
            1,
        )

        self.assertEqual(
            platform.academic_program_links.count(),
            0,
        )

        self.assertEqual(
            platform.knowledge_area_links.count(),
            0,
        )

        self.assertEqual(
            list(
                platform.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            [],
        )

    def test_platform_serializer_ignores_manual_academic_classification(
        self,
    ):
        """La clasificación manual se ignora porque ambos campos son read-only."""
        data = {
            "name": "Scielo",
            "academic_programs": [
                self.academic_program.pk,
                self.academic_program_secondary.pk,
            ],
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        platform = serializer.save(
            created_by=self.system,
        )

        self.assertEqual(
            set(
                platform.academic_program_links.values_list(
                    "academic_program_id",
                    flat=True,
                )
            ),
            set(),
        )

        self.assertEqual(
            set(
                platform.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            set(),
        )

        data = serializers.PlatformSerializer(
            platform,
        ).data

        self.assertEqual(
            set(data["knowledge_areas"]),
            set(),
        )

    def test_platform_serializer_does_not_accept_knowledge_areas_as_input(
        self,
    ):
        """Las knowledge_areas no forman parte de la entrada del usuario."""
        data = {
            "name": "JSTOR",
            "knowledge_areas": [
                self.knowledge_area.pk,
            ],
            "academic_programs": [
                self.academic_program.pk,
            ],
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        self.assertNotIn(
            "knowledge_areas",
            serializer.validated_data,
        )
        self.assertNotIn(
            "academic_programs",
            serializer.validated_data,
        )

        platform = serializer.save(
            created_by=self.system,
        )

        self.assertEqual(
            list(
                platform.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            [],
        )

    def test_platform_serializer_allows_null_api_key_without_base_api_url(
        self,
    ):
        """Una plataforma de referencia puede existir sin API ni API Key."""
        data = {
            "name": "Plataforma Referencia",
            "base_api_url": None,
            "api_key": None,
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        platform = serializer.save(
            created_by=self.system,
        )

        self.assertIsNone(
            platform.base_api_url,
        )

        self.assertIsNone(
            platform.encrypted_api_key,
        )

        self.assertEqual(
            platform.get_api_key(),
            "",
        )

    def test_platform_serializer_allows_base_api_url_without_api_key(
        self,
    ):
        """Una plataforma puede tener API sin requerir una API Key."""
        data = {
            "name": "API Publica",
            "base_api_url": "https://api.publica.org",
            "api_key": None,
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        platform = serializer.save(
            created_by=self.system,
        )

        self.assertEqual(
            platform.base_api_url,
            "https://api.publica.org",
        )

        self.assertIsNone(
            platform.encrypted_api_key,
        )

    def test_platform_serializer_rejects_api_key_without_base_api_url(
        self,
    ):
        """Nunca debe existir una API Key asociada a ninguna API base."""
        data = {
            "name": "Configuracion Invalida",
            "base_api_url": None,
            "api_key": "orphan-key",
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertFalse(
            serializer.is_valid(),
        )

        self.assertIn(
            "base_api_url",
            serializer.errors,
        )

    def test_platform_serializer_clears_api_key_when_sent_as_null(
        self,
    ):
        """Enviar api_key=null elimina una API Key previamente configurada."""
        platform = models.Platform.objects.create(
            name="Plataforma Con API Key",
            base_api_url="https://api.example.org",
            created_by=self.system,
        )

        platform.set_api_key(
            "secret-key",
        )

        platform.save()

        data = {
            "api_key": None,
        }

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data=data,
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        updated = serializer.save(
            updated_by=self.system,
        )

        self.assertIsNone(
            updated.encrypted_api_key,
        )

        self.assertEqual(
            updated.get_api_key(),
            "",
        )

    def test_platform_serializer_rejects_removing_base_api_url_with_existing_api_key(
        self,
    ):
        """No se puede eliminar base_api_url mientras exista una API Key."""
        platform = models.Platform.objects.create(
            name="API Configurada",
            base_api_url="https://api.example.org",
            created_by=self.system,
        )

        platform.set_api_key(
            "secret-key",
        )

        platform.save()

        data = {
            "base_api_url": None,
        }

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data=data,
            partial=True,
        )

        self.assertFalse(
            serializer.is_valid(),
        )

        self.assertIn(
            "base_api_url",
            serializer.errors,
        )

    def test_platform_serializer_allows_removing_base_api_url_and_api_key_together(
        self,
    ):
        """Se pueden eliminar simultáneamente base_api_url y API Key."""
        platform = models.Platform.objects.create(
            name="API A Eliminar",
            base_api_url="https://api.example.org",
            created_by=self.system,
        )

        platform.set_api_key(
            "secret-key",
        )

        platform.save()

        data = {
            "base_api_url": None,
            "api_key": None,
        }

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data=data,
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        updated = serializer.save(
            updated_by=self.system,
        )

        self.assertIsNone(
            updated.base_api_url,
        )

        self.assertIsNone(
            updated.encrypted_api_key,
        )

    def test_platform_serializer_patch_cannot_create_academic_relations(
        self,
    ):
        """Enviar academic_programs por PATCH no crea relaciones derivadas."""
        platform = models.Platform.objects.create(
            name="Plataforma Existente",
            created_by=self.system,
        )

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data={
                "academic_programs": [
                    self.academic_program.pk,
                ],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system,
        )

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data={
                "name": "Plataforma Existente Actualizada",
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        updated = serializer.save(
            updated_by=self.system,
        )

        self.assertEqual(
            list(
                updated.academic_program_links.values_list(
                    "academic_program_id",
                    flat=True,
                )
            ),
            [],
        )

        self.assertEqual(
            list(
                updated.knowledge_area_links.values_list(
                    "knowledge_area_id",
                    flat=True,
                )
            ),
            [],
        )

    def test_platform_serializer_empty_academic_programs_is_read_only(
        self,
    ):
        """Enviar academic_programs=[] no administra relaciones derivadas."""
        platform = models.Platform.objects.create(
            name="Plataforma Clasificada",
            created_by=self.system,
        )

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data={
                "academic_programs": [
                    self.academic_program.pk,
                ],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system,
        )

        self.assertEqual(
            platform.academic_program_links.count(),
            0,
        )

        self.assertEqual(
            platform.knowledge_area_links.count(),
            0,
        )

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data={
                "academic_programs": [],
            },
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        updated = serializer.save(
            updated_by=self.system,
        )

        self.assertEqual(
            updated.academic_program_links.count(),
            0,
        )

        self.assertEqual(
            updated.knowledge_area_links.count(),
            0,
        )

    def test_sync_relations_deduplicates_repeated_ids(self):
        """Una lista con IDs repetidos no debe insertar relaciones duplicadas."""
        platform = models.Platform.objects.create(
            name="Test Duplicates",
            created_by=self.system,
        )

        data = {
            "institutions": [
                self.institution.pk,
                self.institution.pk,
            ],
        }

        serializer = serializers.PlatformSerializer(
            instance=platform,
            data=data,
            partial=True,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        serializer.save(
            updated_by=self.system,
        )

        self.assertEqual(
            platform.support_links.count(),
            1,
        )

    def test_archived_platform_restored_via_serializer_resets_to_draft(
        self,
    ):
        """Una plataforma archivada recreada por nombre debe volver a BORRADOR."""
        platform = models.Platform.objects.create(
            name="Plataforma Archivada",
            status=models.Platform.Status.PUBLICADO,
            validated_by=self.system,
            created_by=self.system,
        )

        platform.soft_delete(
            user=self.system,
            explanation="Eliminada para test",
        )

        data = {
            "name": "Plataforma Archivada",
            "base_api_url": "https://reactivada.org",
        }

        serializer = serializers.PlatformSerializer(
            data=data,
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

        restored = serializer.save(
            created_by=self.system,
        )

        self.assertEqual(
            restored.pk,
            platform.pk,
        )

        self.assertFalse(
            restored.is_deleted,
        )

        self.assertEqual(
            restored.status,
            models.Platform.Status.BORRADOR,
        )

        self.assertIsNone(
            restored.validated_by,
        )

        self.assertIsNone(
            restored.validated_at,
        )

    def test_public_serializer_excludes_sensitive_and_audit_fields(
        self,
    ):
        """PlatformPublicSerializer no debe exponer información interna."""
        platform = models.Platform.objects.create(
            name="Plataforma Publica",
            base_api_url="https://publica.org",
            created_by=self.system,
        )

        platform.set_api_key(
            "secret123",
        )

        platform.save()

        serializer = serializers.PlatformPublicSerializer(
            platform,
        )

        data = serializer.data

        self.assertNotIn(
            "encrypted_api_key",
            data,
        )

        self.assertNotIn(
            "api_key",
            data,
        )

        self.assertNotIn(
            "created_by",
            data,
        )

        self.assertNotIn(
            "delete_explanation",
            data,
        )

        self.assertNotIn(
            "validated_by",
            data,
        )

        self.assertIn(
            "link_status",
            data,
        )

        self.assertIsNone(
            data["link_status"]["is_active"],
        )
