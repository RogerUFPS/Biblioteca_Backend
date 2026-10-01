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

from . import models


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


class ValidSintaxisSerializer(
    ArchivedNameMixin,
    serializers.ModelSerializer,
):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.ValidSintaxis

        fields = [
            *AUDIT_FIELDS,
            "name",
            "booleans",
            "parenthesis",
            "fields",
        ]

        read_only_fields = AUDIT_FIELDS


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

    La identificación de plataformas archivadas y su restauración
    se maneja mediante ArchivedNameMixin.
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
        allow_blank=True,
        help_text=(
            "Clave de API en texto plano; "
            "se almacenará cifrada."
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

    knowledge_areas = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=KnowledgeArea.objects.all(),
        required=False,
        write_only=True,
    )

    material_types = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=MaterialType.objects.all(),
        required=False,
        write_only=True,
    )

    academic_programs = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=AcademicProgram.objects.all(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = models.Platform

        fields = [
            *AUDIT_FIELDS,
            "name",
            "status",
            "base_api_url",
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
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

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

        relation_data = self._extract_relation_data(
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
        raw_api_key = validated_data.pop(
            "api_key",
            None,
        )

        relation_data = self._extract_relation_data(
            validated_data
        )

        platform = super().update(
            instance,
            validated_data,
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

    class Meta:
        model = models.Platform

        fields = [
            "id",
            "name",
            "base_api_url",
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
        latest_log = obj.link_check_logs.first()

        if latest_log:
            return {
                "is_active": latest_log.is_active,
                "last_check": latest_log.last_check,
            }

        return {
            "is_active": None,
            "last_check": None,
        }
        