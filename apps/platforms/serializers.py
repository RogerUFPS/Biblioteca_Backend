from django.db import transaction
from rest_framework import serializers

from drf_spectacular.utils import extend_schema_field

from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.core.serializers import (
    RelationConfig,
    SoftDeleteRelationSyncMixin,
)
from apps.core.viewsets import ArchivedNameMixin

from . import models, services


PLATFORM_RELATION_CONFIG = (
    RelationConfig(
        data_field="institutions",
        through_model=models.SharedPlatformSupport,
        relation_field="institution",
    ),
    RelationConfig(
        data_field="languages",
        through_model=models.SharedPlatformLanguage,
        relation_field="language",
    ),
    RelationConfig(
        data_field="countries",
        through_model=models.SharedPlatformCountry,
        relation_field="country",
    ),
    RelationConfig(
        data_field="knowledge_areas",
        through_model=models.SharedPlatformKnowledgeArea,
        relation_field="knowledge_area",
    ),
    RelationConfig(
        data_field="material_types",
        through_model=models.SharedPlatformMaterialType,
        relation_field="material_type",
    ),
    RelationConfig(
        data_field="academic_programs",
        through_model=models.SharedPlatformAcademicProgram,
        relation_field="academic_program",
    ),
)


AUDIT_FIELDS = (
    "id",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "deleted_by",
    "deleted_at",
    "delete_explanation",
)


VALID_SINTAXIS_FIELD_KEYS = (
    "title",
    "author",
    "subject",
    "issn",
    "language",
    "year",
)


"""
Plantilla inmutable para el campo ``fields`` de ValidSintaxis.

Las claves canónicas permitidas se mantienen en una tupla inmutable.
El valor almacenado en ``fields`` contiene el prefijo/parámetro que
la plataforma utiliza para cada campo.

Ejemplo::

    {
        "title":    "ti",
        "author":   "au",
        "subject":  "su",
        "issn":     "is",
        "language": "la",
        "year":     "yr"
    }
"""


class ValidSintaxisSerializer(
    ArchivedNameMixin,
    serializers.ModelSerializer,
):
    archived_unique_fields = ("name",)

    fields_template = serializers.SerializerMethodField(
        read_only=True,
        help_text=(
            "Plantilla de referencia para construir el campo ``fields``. "
            "Muestra las claves canónicas admitidas con sus valores vacíos."
        ),
    )

    class Meta:
        model = models.ValidSintaxis

        fields = [
            *AUDIT_FIELDS,
            "name",
            "booleans",
            "parenthesis",
            "fields",
            "fields_template",
        ]

        read_only_fields = [
            *AUDIT_FIELDS,
            "fields_template",
        ]

        extra_kwargs = {
            "fields": {
                "help_text": (
                    "Mapeo de campos semánticos a prefijos de la API. "
                    "Use ``fields_template`` como referencia de las claves disponibles. "
                    "Ejemplo: {\"title\": \"ti\", \"author\": \"au\", \"issn\": \"is\"}"
                ),
            }
        }

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_fields_template(self, obj):
        return {key: "" for key in VALID_SINTAXIS_FIELD_KEYS}

    def validate_fields(self, value):
        """
        Valida que el campo ``fields`` sea un diccionario plano
        de strings y que sus claves sean un subconjunto de la
        plantilla canónica.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "El campo debe ser un objeto JSON (diccionario)."
            )

        allowed_keys = set(VALID_SINTAXIS_FIELD_KEYS)
        invalid_keys = set(value.keys()) - allowed_keys

        if invalid_keys:
            raise serializers.ValidationError(
                f"Las siguientes claves no están permitidas: "
                f"{sorted(invalid_keys)}. "
                f"Claves válidas: {sorted(allowed_keys)}."
            )

        for key, val in value.items():
            if not isinstance(val, str):
                raise serializers.ValidationError(
                    f"El valor de la clave '{key}' debe ser una cadena de texto."
                )

        return value


class ValidSintaxisPublicSerializer(
    serializers.ModelSerializer,
):
    class Meta:
        model = models.ValidSintaxis

        fields = [
            "name",
            "booleans",
            "parenthesis",
            "fields",
        ]


class LinkCheckLogSerializer(
    serializers.ModelSerializer,
):
    class Meta:
        model = models.LinkCheckLog

        fields = [
            *AUDIT_FIELDS,
            "platform",
            "journal_platform",
            "url",
            "fail_count",
            "http_status_code",
            "is_active",
            "last_check",
        ]

        read_only_fields = AUDIT_FIELDS


class PlatformSerializer(
    SoftDeleteRelationSyncMixin,
    ArchivedNameMixin,
    serializers.ModelSerializer,
):
    """
    Serializador administrativo de plataformas.

    Las relaciones mediante tablas intermedias se sincronizan
    mediante SoftDeleteRelationSyncMixin.

    La relación con áreas del conocimiento no se recibe directamente
    del cliente: se deriva automáticamente a partir de los programas
    académicos seleccionados y de SharedAcademicProgramKnowledgeArea.
    """

    archived_unique_fields = ("name",)

    relation_config = PLATFORM_RELATION_CONFIG
    relation_parent_field = "platform"

    relation_delete_explanation = (
        "Relación eliminada durante la actualización "
        "de la plataforma."
    )

    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text=(
            "Clave de API en texto plano; es opcional. "
            "Solo puede configurarse si existe base_api_url. "
            "Se almacenará cifrada."
        ),
    )

    public_url = serializers.SerializerMethodField(
        help_text=(
            "URL pública navegable obtenida del último LinkCheckLog "
            "general no eliminado. No corresponde a base_api_url."
        )
    )

    base_api_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text=(
            "URL base de la API utilizada para cosecha automatizada. "
            "Es opcional cuando la plataforma solo se registra como referencia. "
            "Si se configura una API Key, esta URL es obligatoria."
        ),
    )

    institutions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Institution.objects.all(),
        required=False,
        write_only=True,
    )

    languages = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Language.objects.all(),
        required=False,
        write_only=True,
    )

    countries = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Country.objects.all(),
        required=False,
        write_only=True,
    )

    # Las áreas no son un dato de entrada. Se calculan a partir de los
    # programas académicos y se exponen únicamente en la representación.
    knowledge_areas = serializers.ListField(
        child=serializers.IntegerField(),
        read_only=True,
        help_text=(
            "Áreas del conocimiento derivadas automáticamente de los "
            "programas académicos asociados."
        ),
    )

    material_types = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=MaterialType.objects.all(),
        required=False,
        write_only=True,
    )

    academic_programs = serializers.ListField(
        child=serializers.IntegerField(),
        read_only=True,
        help_text=(
            "Programas derivados automáticamente de las revistas elegibles "
            "asociadas a la plataforma."
        ),
    )

    class Meta:
        model = models.Platform

        fields = [
            *AUDIT_FIELDS,
            "name",
            "status",
            "base_api_url",
            "public_url",
            "api_key",
            "url_image",
            "start_period",
            "finish_period",
            "requires_registration",
            "has_access_text",
            "validated_by",
            "validated_at",
            "valid_sintaxis",
            "institutions",
            "languages",
            "countries",
            "knowledge_areas",
            "material_types",
            "academic_programs",
        ]
        read_only_fields = [
            *AUDIT_FIELDS,
            "status",
            "validated_by",
            "validated_at",
            "knowledge_areas",
            "academic_programs",
            "public_url",
        ]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_public_url(self, obj):
        latest_log = services.latest_platform_link_log(obj)
        return latest_log.url if latest_log else None

    def validate_base_api_url(self, value):
        """Normaliza una URL base vacía a ``None``."""
        if value == "":
            return None

        return value

    def validate_api_key(self, value):
        """Normaliza una API Key vacía a ``None``."""
        if value == "":
            return None

        return value

    def validate(self, attrs):
        """
        Valida las reglas de configuración de la cosecha.

        - Una plataforma puede existir sin API Key.
        - Una plataforma puede existir sin base_api_url si solo funciona
        como referencia pública.
        - Nunca se permite conservar/configurar una API Key sin una
        base_api_url correspondiente.
        - Las knowledge_areas se derivan automáticamente de los
        academic_programs.
        """
        attrs = super().validate(attrs)

        instance = self.instance

        if "base_api_url" in attrs:
            effective_base_api_url = attrs["base_api_url"]
        elif instance is not None:
            effective_base_api_url = instance.base_api_url
        else:
            effective_base_api_url = None

        if "api_key" in attrs:
            effective_api_key = attrs["api_key"]
            has_api_key = bool(effective_api_key)
        elif instance is not None:
            has_api_key = bool(instance.encrypted_api_key)
        else:
            has_api_key = False

        if has_api_key and not effective_base_api_url:
            raise serializers.ValidationError(
                {
                    "base_api_url": (
                        "No se puede configurar una API Key sin una URL base "
                        "de la API (base_api_url)."
                    )
                }
            )

        return attrs

    def _prepare_relation_data(self, validated_data):
        """
        Extrae las relaciones recibidas y deriva las knowledge_areas
        cuando el cliente ha enviado academic_programs.

        Si academic_programs no fue enviado, las relaciones existentes
        no se modifican.
        """
        return self._extract_relation_data(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(
            instance
        )

        return self._represent_relations(
            instance=instance,
            representation=representation,
        )

    @transaction.atomic
    def create(self, validated_data):
        raw_api_key = validated_data.pop(
            "api_key",
            None,
        )

        relation_data = self._prepare_relation_data(
            validated_data
        )

        platform = super().create(
            validated_data
        )

        was_archived = (
            getattr(
                self,
                "_archived_instance",
                None,
            )
            is not None
        )

        if was_archived:
            platform.status = (
                models.Platform.Status.BORRADOR
            )

            platform.validated_by = None
            platform.validated_at = None

            platform.save(
                update_fields=[
                    "status",
                    "validated_by",
                    "validated_at",
                ]
            )

        if raw_api_key is not None:
            platform.set_api_key(
                raw_api_key
            )

            platform.save(
                update_fields=[
                    "encrypted_api_key",
                ]
            )

        if relation_data:
            self._sync_relations(
                parent=platform,
                relation_data=relation_data,
            )

        return platform

    @transaction.atomic
    def update(
        self,
        instance,
        validated_data,
    ):
        api_key_was_sent = "api_key" in validated_data

        raw_api_key = validated_data.pop(
            "api_key",
            None,
        )

        relation_data = self._prepare_relation_data(
            validated_data
        )

        platform = super().update(
            instance,
            validated_data,
        )

        if api_key_was_sent:
            platform.set_api_key(
                raw_api_key
            )

            platform.save(
                update_fields=[
                    "encrypted_api_key",
                ]
            )

        if relation_data:
            self._sync_relations(
                parent=platform,
                relation_data=relation_data,
            )

        return platform


# ==============================================================================
# ESQUEMAS DE RESPUESTA PÚBLICA PARA SWAGGER
# ==============================================================================


class PlatformPublicInstitutionSchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PlatformPublicLanguageSchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    abbreviation = serializers.CharField()


class PlatformPublicCountrySchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    abbreviation = serializers.CharField()
    emoji_flag = serializers.CharField(
        allow_blank=True,
        allow_null=True,
    )


class PlatformPublicKnowledgeAreaSchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PlatformPublicMaterialTypeSchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PlatformPublicAcademicProgramSchemaSerializer(
    serializers.Serializer,
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PlatformPublicLinkStatusSchemaSerializer(
    serializers.Serializer,
):
    url = serializers.URLField(
        allow_null=True,
        help_text=(
            "URL pública de la plataforma registrada "
            "en el último chequeo."
        ),
    )

    is_active = serializers.BooleanField(
        allow_null=True,
    )

    last_check = serializers.DateTimeField(
        allow_null=True,
    )


class PlatformPublicSerializer(
    serializers.ModelSerializer,
):
    """
    Serializador de solo lectura para la exploración pública.

    No expone:

    - encrypted_api_key;
    - campos de auditoría interna;
    - datos internos de validación.
    """

    valid_sintaxis = ValidSintaxisPublicSerializer(
        read_only=True
    )

    institutions = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    countries = serializers.SerializerMethodField()
    knowledge_areas = serializers.SerializerMethodField()
    material_types = serializers.SerializerMethodField()
    academic_programs = serializers.SerializerMethodField()
    link_status = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField(
        help_text=(
            "URL pública navegable obtenida del último LinkCheckLog "
            "general no eliminado."
        )
    )

    class Meta:
        model = models.Platform

        fields = [
            "id",
            "name",
            "base_api_url",
            "public_url",
            "url_image",
            "start_period",
            "finish_period",
            "requires_registration",
            "has_access_text",
            "valid_sintaxis",
            "institutions",
            "languages",
            "countries",
            "knowledge_areas",
            "material_types",
            "academic_programs",
            "link_status",
        ]

    @extend_schema_field(
        PlatformPublicInstitutionSchemaSerializer(many=True)
    )
    def get_institutions(self, obj):
        return list(
            Institution.objects.filter(
                platform_support_links__platform=obj,
                platform_support_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        PlatformPublicLanguageSchemaSerializer(many=True)
    )
    def get_languages(self, obj):
        return list(
            Language.objects.filter(
                platform_links__platform=obj,
                platform_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
                "abbreviation",
            )
        )

    @extend_schema_field(
        PlatformPublicCountrySchemaSerializer(many=True)
    )
    def get_countries(self, obj):
        return list(
            Country.objects.filter(
                platform_links__platform=obj,
                platform_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
                "abbreviation",
                "emoji_flag",
            )
        )

    @extend_schema_field(
        PlatformPublicKnowledgeAreaSchemaSerializer(many=True)
    )
    def get_knowledge_areas(self, obj):
        return list(
            KnowledgeArea.objects.filter(
                platform_links__platform=obj,
                platform_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        PlatformPublicMaterialTypeSchemaSerializer(many=True)
    )
    def get_material_types(self, obj):
        return list(
            MaterialType.objects.filter(
                platform_links__platform=obj,
                platform_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        PlatformPublicAcademicProgramSchemaSerializer(many=True)
    )
    def get_academic_programs(self, obj):
        return list(
            AcademicProgram.objects.filter(
                platform_links__platform=obj,
                platform_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        PlatformPublicLinkStatusSchemaSerializer
    )
    def get_link_status(self, obj):
        latest_log = services.latest_platform_link_log(obj)

        if latest_log:
            return {
                "url": latest_log.url,
                "is_active": latest_log.is_active,
                "last_check": latest_log.last_check,
            }

        return {
            "url": None,
            "is_active": None,
            "last_check": None,
        }

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_public_url(self, obj):
        latest_log = services.latest_platform_link_log(obj)
        return latest_log.url if latest_log else None
