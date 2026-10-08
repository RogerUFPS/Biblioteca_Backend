from typing import Any, cast

from rest_framework.response import Response
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.platforms import models, services


class PlatformAPITests(APITestCase):
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

        cls.material_type = MaterialType.objects.create(
            name="Artículos",
            created_by=cls.system,
        )

        cls.academic_program = AcademicProgram.objects.create(
            name="Ingeniería de Sistemas",
            created_by=cls.system,
        )

        cls.sintaxis = models.ValidSintaxis.objects.create(
            name="Sintaxis Estandar",
            booleans=["AND", "OR"],
            parenthesis=True,
            fields={"title": "ti"},
            created_by=cls.system,
        )

    def _get_data(self, response: Any) -> dict[str, Any]:
        """Helper para obtener el payload asegurando el tipado estático."""
        return getattr(response, "data", {})

    def _setup_complete_platform(
        self,
        name="Plataforma API Test",
    ):
        platform = models.Platform.objects.create(
            name=name,
            is_harvestable=True,
            base_api_url="https://api.test.org",
            start_period="2000-01-01",
            valid_sintaxis=self.sintaxis,
            created_by=self.system,
        )

        models.SharedPlatformSupport.objects.create(
            platform=platform,
            institution=self.institution,
            created_by=self.system,
        )

        models.SharedPlatformLanguage.objects.create(
            platform=platform,
            language=self.language,
            created_by=self.system,
        )

        models.SharedPlatformCountry.objects.create(
            platform=platform,
            country=self.country,
            created_by=self.system,
        )

        models.SharedPlatformKnowledgeArea.objects.create(
            platform=platform,
            knowledge_area=self.knowledge_area,
            created_by=self.system,
        )

        models.SharedPlatformMaterialType.objects.create(
            platform=platform,
            material_type=self.material_type,
            created_by=self.system,
        )

        models.SharedPlatformAcademicProgram.objects.create(
            platform=platform,
            academic_program=self.academic_program,
            created_by=self.system,
        )

        # La URL pública pertenece a LinkCheckLog y es requisito
        # para publicar la plataforma.
        models.LinkCheckLog.objects.create(
            platform=platform,
            url="https://www.plataforma-api-test.org",
            fail_count=0,
            http_status_code=200,
            is_active=True,
            created_by=self.system,
        )

        return platform

    def test_create_platform_endpoint(self):
        """Verifica la creacion administrativa via POST /api/platforms/."""
        response = self.client.post(
            "/api/platforms/",
            {
                "name": "Scopus API Test",
                "public_url": "https://8.8.8.8/scopus",
                "is_harvestable": True,
                "base_api_url": "https://api.scopus.com",
                "api_key": "raw_secret_key",
                "start_period": "2010-01-01",
                "valid_sintaxis": self.sintaxis.pk,
                "institutions": [self.institution.pk],
            },
            format="json",
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            data["name"],
            "scopus api test",
        )

        self.assertNotIn(
            "encrypted_api_key",
            data,
        )
        self.assertNotIn("api_key", data)
        self.assertEqual(data["public_url"], "https://8.8.8.8/scopus")
        self.assertTrue(data["is_harvestable"])
        platform = models.Platform.objects.get(pk=data["id"])
        self.assertFalse(hasattr(platform, "public_url"))
        self.assertTrue(
            models.LinkCheckLog.objects.filter(
                platform=platform,
                journal_platform__isnull=True,
                url="https://8.8.8.8/scopus",
            ).exists()
        )

    def test_publish_action_endpoint(self):
        """Verifica la accion POST /api/platforms/{id}/publish/."""
        platform = self._setup_complete_platform()

        response = self.client.post(
            f"/api/platforms/{platform.pk}/publish/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            data["status"],
            models.Platform.Status.PUBLICADO,
        )

    def test_restore_action_resets_status_to_draft(self):
        """Verifica que restaurar una plataforma por endpoint la devuelva a BORRADOR."""
        platform = self._setup_complete_platform()

        services.publish_platform(
            platform=platform,
            user=self.system,
        )

        platform.soft_delete(
            user=self.system,
            explanation="Eliminando ficha activa",
        )

        response = self.client.post(
            f"/api/platforms/{platform.pk}/restore/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            data["status"],
            models.Platform.Status.BORRADOR,
        )

        self.assertIsNone(
            data["validated_by"],
        )

        self.assertIsNone(
            data["validated_at"],
        )

    def test_public_endpoint_only_lists_published_platforms(self):
        """El endpoint publico solo debe retornar plataformas en estado PUBLICADO."""
        self._setup_complete_platform(
            "Borrador Oculto"
        )

        pub = self._setup_complete_platform(
            "Publica Visible"
        )

        services.publish_platform(
            platform=pub,
            user=self.system,
        )

        response = self.client.get(
            "/api/platforms/public/"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        results = data["results"]

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0]["name"],
            "publica visible",
        )

        self.assertIn(
            "item_number",
            results[0],
        )

    def test_public_filter_by_catalog_relations(self):
        """Verifica los filtros en singular para catalogos en el endpoint publico."""
        pub = self._setup_complete_platform(
            "Publica Filtrable"
        )

        services.publish_platform(
            platform=pub,
            user=self.system,
        )

        response = self.client.get(
            f"/api/platforms/public/?country={self.country.pk}"
        )

        data = self._get_data(response)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(data["results"]),
            1,
        )

        response_empty = self.client.get(
            "/api/platforms/public/?country=99999"
        )

        data_empty = self._get_data(
            response_empty
        )

        self.assertEqual(
            response_empty.status_code,
            200,
        )

        self.assertEqual(
            len(data_empty["results"]),
            0,
        )
