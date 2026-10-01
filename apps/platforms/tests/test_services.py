from unittest.mock import patch
from django.test import TestCase
from rest_framework.exceptions import ValidationError

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


class PlatformServicesTests(TestCase):
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

    def _setup_complete_platform(self):
        platform = models.Platform.objects.create(
            name="Plataforma Completa",
            base_api_url="https://api.completa.org",
            start_period="2000-01-01",
            valid_sintaxis=self.sintaxis,
            created_by=self.system,
        )
        models.SharedPlatformSupport.objects.create(platform=platform, institution=self.institution, created_by=self.system)
        models.SharedPlatformLanguage.objects.create(platform=platform, language=self.language, created_by=self.system)
        models.SharedPlatformCountry.objects.create(platform=platform, country=self.country, created_by=self.system)
        models.SharedPlatformKnowledgeArea.objects.create(platform=platform, knowledge_area=self.knowledge_area, created_by=self.system)
        models.SharedPlatformMaterialType.objects.create(platform=platform, material_type=self.material_type, created_by=self.system)
        models.SharedPlatformAcademicProgram.objects.create(platform=platform, academic_program=self.academic_program, created_by=self.system)
        return platform

    def test_publish_platform_succeeds_when_complete(self):
        """Verifica que una plataforma con toda la ficha valida pase a PUBLICADO."""
        platform = self._setup_complete_platform()
        published = services.publish_platform(platform=platform, user=self.system)

        self.assertEqual(published.status, models.Platform.Status.PUBLICADO)
        self.assertEqual(published.validated_by, self.system)
        self.assertIsNotNone(published.validated_at)

    def test_publish_platform_fails_when_incomplete(self):
        """Verifica que la publicacion falle si faltan relaciones o campos obligatorios."""
        platform = models.Platform.objects.create(
            name="Plataforma Incompleta",
            created_by=self.system,
        )
        with self.assertRaises(ValidationError) as context:
            services.publish_platform(platform=platform, user=self.system)

        errors = context.exception.detail
        self.assertIn("base_api_url", errors)
        self.assertIn("start_period", errors)
        self.assertIn("valid_sintaxis", errors)
        self.assertIn("institutions", errors)

    def test_lifecycle_transitions_obsolete_and_reactivate(self):
        """Verifica la transicion de PUBLICADO a OBSOLETO y reactivacion a BORRADOR."""
        platform = self._setup_complete_platform()
        services.publish_platform(platform=platform, user=self.system)

        obsolete = services.mark_platform_obsolete(platform=platform, user=self.system)
        self.assertEqual(obsolete.status, models.Platform.Status.OBSOLETO)
        self.assertIsNotNone(obsolete.validated_by)

        reactivated = services.reactivate_platform(platform=platform, user=self.system)
        self.assertEqual(reactivated.status, models.Platform.Status.BORRADOR)
        self.assertIsNone(reactivated.validated_by)
        self.assertIsNone(reactivated.validated_at)

    def test_validate_safe_http_url_blocks_internal_and_private_ips(self):
        """Verifica que la validacion SSRF rechace localhost y redes privadas."""
        with self.assertRaises(ValidationError):
            services._validate_safe_http_url("http://localhost:8000/api")

        with self.assertRaises(ValidationError):
            services._validate_safe_http_url("http://127.0.0.1/test")

        with self.assertRaises(ValidationError):
            services._validate_safe_http_url("http://192.168.1.1/api")

    @patch("apps.platforms.services._perform_link_check")
    @patch("apps.platforms.services._validate_safe_http_url")
    def test_check_platform_link_records_consecutive_fail_count(self, mock_validate, mock_check):
        """Verifica el incremento y reinicio de fail_count en chequeos sucesivos."""
        platform = models.Platform.objects.create(
            name="Plataforma Link Test",
            base_api_url="https://api.externa.org",
            created_by=self.system,
        )

        mock_check.return_value = (500, False)
        log1 = services.check_platform_link(platform=platform, user=self.system)
        self.assertEqual(log1.fail_count, 1)
        self.assertFalse(log1.is_active)

        log2 = services.check_platform_link(platform=platform, user=self.system)
        self.assertEqual(log2.fail_count, 2)

        mock_check.return_value = (200, True)
        log3 = services.check_platform_link(platform=platform, user=self.system)
        self.assertEqual(log3.fail_count, 0)
        self.assertTrue(log3.is_active)
