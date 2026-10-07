from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import AuditableModel
from apps.core.utils.crypto import decrypt_api_key, encrypt_api_key

from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)


class ValidSintaxis(AuditableModel):

    name = models.CharField(max_length=150)
    booleans = models.JSONField(
        default=list,
        help_text="Lista de operadores booleanos admitidos. Ej: ['AND', 'OR', 'NOT']"
    )
    parenthesis = models.BooleanField(
        default=True,
        help_text="Indica si la plataforma soporta agrupación por paréntesis."
    )
    fields = models.JSONField(
        default=dict,
        help_text="Mapeo de campos admitidos. Ej: {'title': 'ti', 'language': 'la'}"
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_valid_sintaxis_name_ci",
            )
        ]

    def __str__(self):
        return self.name


class Platform(AuditableModel):
    
    class Status(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PUBLICADO = "publicado", "Publicado"
        OBSOLETO = "obsoleto", "Obsoleto"

    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.BORRADOR,
        help_text="Estado del ciclo de vida de la ficha."
    )
    base_api_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL base de la API para cosecha automatizada.",
    )
    encrypted_api_key = models.TextField(null=True, blank=True)
    url_image = models.URLField(max_length=500, null=True, blank=True)
    
    start_period = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha o período inicial de cobertura."
    )
    finish_period = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha o período final de cobertura (vacío si continúa activo)."
    )
    
    requires_registration = models.BooleanField(
        default=False,
        help_text="Indica si el usuario debe crear cuenta para consultar."
    )
    has_access_text = models.BooleanField(
        default=False,
        help_text="Indica si ofrece acceso a texto completo."
    )

    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_platforms",
    )
    validated_at = models.DateTimeField(null=True, blank=True)

    valid_sintaxis = models.ForeignKey(
        ValidSintaxis,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="platforms",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_platform_name_ci",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def set_api_key(self, raw_key: str | None):
        """Cifra y asigna la API Key en el campo encrypted_api_key."""
        self.encrypted_api_key = encrypt_api_key(raw_key) if raw_key else None

    def get_api_key(self) -> str:
        """Descifra y retorna la API Key en texto plano."""
        if not self.encrypted_api_key:
            return ""
        return decrypt_api_key(self.encrypted_api_key)


class LinkCheckLog(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="link_check_logs",
    )
    url = models.URLField(max_length=500)
    fail_count = models.PositiveIntegerField(
        default=0,
        help_text="Número consecutivo de comprobaciones fallidas."
    )
    http_status_code = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Indica si el enlace respondió correctamente en el último chequeo."
    )
    last_check = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_check", "-created_at"]

    def __str__(self):
        return f"LinkCheck: {self.platform.name} - Status: {self.http_status_code} (Fails: {self.fail_count})"


# ==============================================================================
# TABLAS INTERMEDIAS DE CLASIFICACIÓN (SharedPlatform*)
# ==============================================================================

class SharedPlatformSupport(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="support_links",
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        related_name="platform_support_links",
    )

    class Meta:
        ordering = ["platform_id", "institution_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "institution"],
                name="unique_platform_institution",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.institution}"


class SharedPlatformLanguage(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="language_links",
    )
    language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name="platform_links",
    )

    class Meta:
        ordering = ["platform_id", "language_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "language"],
                name="unique_platform_language",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.language}"


class SharedPlatformCountry(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="country_links",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="platform_links",
    )

    class Meta:
        ordering = ["platform_id", "country_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "country"],
                name="unique_platform_country",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.country}"


class SharedPlatformKnowledgeArea(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="knowledge_area_links",
    )
    knowledge_area = models.ForeignKey(
        KnowledgeArea,
        on_delete=models.PROTECT,
        related_name="platform_links",
    )

    class Meta:
        ordering = ["platform_id", "knowledge_area_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "knowledge_area"],
                name="unique_platform_knowledge_area",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.knowledge_area}"


class SharedPlatformMaterialType(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="material_type_links",
    )
    material_type = models.ForeignKey(
        MaterialType,
        on_delete=models.PROTECT,
        related_name="platform_links",
    )

    class Meta:
        ordering = ["platform_id", "material_type_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "material_type"],
                name="unique_platform_material_type",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.material_type}"


class SharedPlatformAcademicProgram(AuditableModel):
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="academic_program_links",
    )
    academic_program = models.ForeignKey(
        AcademicProgram,
        on_delete=models.PROTECT,
        related_name="platform_links",
    )

    class Meta:
        ordering = ["platform_id", "academic_program_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "academic_program"],
                name="unique_platform_academic_program",
            )
        ]

    def __str__(self):
        return f"{self.platform} <-> {self.academic_program}"
