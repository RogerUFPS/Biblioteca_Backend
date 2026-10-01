from django.test import TestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
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
        cls.institution = Institution.objects.create(name="UFPS", created_by=cls.system)
        cls.language = Language.objects.create(name="Español", abbreviation="es", created_by=cls.system)
        cls.country = Country.objects.create(name="Colombia", abbreviation="co", emoji_flag="🇨🇴", created_by=cls.system)
        cls.knowledge_area = KnowledgeArea.objects.create(name="Ingeniería", created_by=cls.system)
        cls.material_type = MaterialType.objects.create(name="Artículos", created_by=cls.system)
        cls.academic_program = AcademicProgram.objects.create(name="Ingeniería de Sistemas", created_by=cls.system)
        cls.sintaxis = models.ValidSintaxis.objects.create(
            name="Sintaxis Estandar",
            booleans=["AND", "OR"],
            parenthesis=True,
            fields={"title": "ti"},
            created_by=cls.system,
        )

    def test_platform_serializer_create_with_api_key_and_relations(self):
        """Verifica que el serializer administrativo persista api_key cifrada y sincronice M2M."""
        data = {
            "name": "Redalyc",
            "base_api_url": "https://www.redalyc.org",
            "api_key": "my-plain-text-key",
            "start_period": "2000-01-01",
            "valid_sintaxis": self.sintaxis.pk,
            "institutions": [self.institution.pk],
            "languages": [self.language.pk],
            "countries": [self.country.pk],
            "knowledge_areas": [self.knowledge_area.pk],
            "material_types": [self.material_type.pk],
            "academic_programs": [self.academic_program.pk],
        }
        serializer = serializers.PlatformSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        platform = serializer.save(created_by=self.system)

        self.assertEqual(platform.status, models.Platform.Status.BORRADOR)
        self.assertEqual(platform.get_api_key(), "my-plain-text-key")
        self.assertEqual(platform.support_links.count(), 1)
        self.assertEqual(platform.country_links.count(), 1)

    def test_sync_relations_deduplicates_repeated_ids(self):
        """Verifica que una lista con IDs repetidos no intente insertar duplicados."""
        platform = models.Platform.objects.create(
            name="Test Duplicates",
            created_by=self.system,
        )
        data = {
            "institutions": [self.institution.pk, self.institution.pk],
        }
        serializer = serializers.PlatformSerializer(instance=platform, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(updated_by=self.system)

        self.assertEqual(platform.support_links.count(), 1)

    def test_archived_platform_restored_via_serializer_resets_to_draft(self):
        """Si una plataforma eliminada se recrea con el mismo nombre, debe revivir en BORRADOR."""
        platform = models.Platform.objects.create(
            name="Plataforma Archivada",
            status=models.Platform.Status.PUBLICADO,
            validated_by=self.system,
            created_by=self.system,
        )
        platform.soft_delete(user=self.system, explanation="Eliminada para test")

        data = {
            "name": "Plataforma Archivada",
            "base_api_url": "https://reactivada.org",
        }
        serializer = serializers.PlatformSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        restored = serializer.save(created_by=self.system)

        self.assertEqual(restored.pk, platform.pk)
        self.assertFalse(restored.is_deleted)
        self.assertEqual(restored.status, models.Platform.Status.BORRADOR)
        self.assertIsNone(restored.validated_by)
        self.assertIsNone(restored.validated_at)

    def test_public_serializer_excludes_sensitive_and_audit_fields(self):
        """PlatformPublicSerializer no debe exponer api_key ni campos internos de auditoria."""
        platform = models.Platform.objects.create(
            name="Plataforma Publica",
            base_api_url="https://publica.org",
            created_by=self.system,
        )
        platform.set_api_key("secret123")
        platform.save()

        serializer = serializers.PlatformPublicSerializer(platform)
        data = serializer.data

        self.assertNotIn("encrypted_api_key", data)
        self.assertNotIn("api_key", data)
        self.assertNotIn("created_by", data)
        self.assertNotIn("delete_explanation", data)
        self.assertNotIn("validated_by", data)
        self.assertIn("link_status", data)
        self.assertIsNone(data["link_status"]["is_active"])
