from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.catalog.models import Editorial, Language


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
        editorial = Editorial.objects.create(
            name="Editorial de prueba",
            created_by=self.system,
        )

        response = self.client.delete(
            f"/api/catalog/editorials/{editorial.pk}/",
            {"delete_explanation": "Registro de prueba"},
            format="json",
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Editorial.objects.filter(pk=editorial.pk).exists())
        self.assertTrue(Editorial.all_objects.filter(pk=editorial.pk).exists())

        response = self.client.post(
            f"/api/catalog/editorials/{editorial.pk}/restore/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Editorial.objects.filter(pk=editorial.pk).exists())

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
