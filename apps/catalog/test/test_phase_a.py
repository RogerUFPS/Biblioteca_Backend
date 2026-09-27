from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    KnowledgeArea,
    Language,
    SharedAcademicProgramKnowledgeArea,
)


class PhaseATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )

    def setUp(self):
        self.client = APIClient()

    def test_catalog_create_uses_system_user(self):
        response = self.client.post(
            "/api/catalog/languages/",
            {"abbreviation": "es", "name": "Español"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.system.pk)

    def test_catalog_names_are_normalized_to_lowercase(self):
        response = self.client.post(
            "/api/catalog/knowledge-areas/",
            {"name": "  Ingeniería de Datos  "},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "ingeniería de datos")

    def test_catalog_name_is_case_insensitive_for_uniqueness(self):
        country = Country.objects.create(
            name="colombia",
            abbreviation="co",
            emoji_flag="🇨🇴",
            created_by=self.system,
        )
        Country.all_objects.filter(pk=country.pk).update(name="Colombia")

        response = self.client.post(
            "/api/catalog/countries/",
            {
                "name": "Colombia",
                "abbreviation": "co-2",
                "emoji_flag": "🇨🇴",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_database_constraint_rejects_case_insensitive_duplicate(self):
        Country.objects.create(
            name="colombia",
            abbreviation="co",
            emoji_flag="🇨🇴",
            created_by=self.system,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Country.objects.create(
                    name="COLOMBIA",
                    abbreviation="co-2",
                    emoji_flag="🇨🇴",
                    created_by=self.system,
                )

    def test_catalog_update_sets_updated_fields(self):
        language = Language.objects.create(
            abbreviation="es",
            name="Español",
            created_by=self.system,
        )

        response = self.client.patch(
            f"/api/catalog/languages/{language.pk}/",
            {"name": "Castellano"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        language.refresh_from_db()
        self.assertEqual(language.updated_by, self.system)
        self.assertIsNotNone(language.updated_at)

    def test_delete_requires_explanation_and_restore_works(self):
        area = KnowledgeArea.objects.create(
            name="Área de prueba",
            created_by=self.system,
        )
        program = AcademicProgram.objects.create(
            name="Programa de prueba",
            created_by=self.system,
        )
        relation = SharedAcademicProgramKnowledgeArea.objects.create(
            knowledge_area=area,
            academic_program=program,
            created_by=self.system,
        )

        response = self.client.delete(
            f"/api/catalog/knowledge-areas/{area.pk}/",
            {"delete_explanation": "Registro de prueba"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["permanent"])
        self.assertFalse(KnowledgeArea.objects.filter(pk=area.pk).exists())
        self.assertTrue(KnowledgeArea.all_objects.filter(pk=area.pk).exists())

        response = self.client.post(
            f"/api/catalog/knowledge-areas/{area.pk}/restore/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(KnowledgeArea.objects.filter(pk=area.pk).exists())
        relation.refresh_from_db()

    def test_delete_without_relations_is_permanent(self):
        editorial = Editorial.objects.create(
            name="Editorial permanente",
            created_by=self.system,
        )

        response = self.client.delete(
            f"/api/catalog/editorials/{editorial.pk}/",
            {"delete_explanation": "Limpieza de prueba"},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Editorial.all_objects.filter(pk=editorial.pk).exists())

    def test_archived_endpoint_lists_deleted_records_only(self):
        archived = Editorial.objects.create(
            name="Editorial archivada para listar",
            created_by=self.system,
        )
        archived.soft_delete(self.system, "Prueba de archivados")
        Editorial.objects.create(
            name="Editorial activa para listar",
            created_by=self.system,
        )

        response = self.client.get("/api/catalog/editorials/archived/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], archived.pk)
        self.assertIsNotNone(response.data["results"][0]["deleted_at"])

    def test_archived_unique_value_is_restored_automatically(self):
        editorial = Editorial.objects.create(
            name="Editorial archivada",
            created_by=self.system,
        )
        editorial.soft_delete(self.system, "Ya no se usa")

        response = self.client.post(
            "/api/catalog/editorials/",
            {"name": "Editorial archivada"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["id"], editorial.pk)
        self.assertIsNone(response.data["deleted_at"])
        self.assertTrue(Editorial.objects.filter(pk=editorial.pk).exists())

    def test_delete_without_explanation_returns_bad_request(self):
        editorial = Editorial.objects.create(
            name="Editorial sin explicación",
            created_by=self.system,
        )

        response = self.client.delete(
            f"/api/catalog/editorials/{editorial.pk}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
