from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import (
    AcademicProgram,
    Country,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.core.viewsets import ArchivedNameMixin

from . import models

PLATFORM_RELATION_CONFIG = (
    # (data_field, through_model, relation_field, manager_name, id_field)
    ("institutions",      models.SharedPlatformSupport,       "institution",     "support_links",          "institution_id"),
    ("languages",         models.SharedPlatformLanguage,      "language",        "language_links",         "language_id"),
    ("countries",         models.SharedPlatformCountry,       "country",         "country_links",          "country_id"),
    ("knowledge_areas",   models.SharedPlatformKnowledgeArea, "knowledge_area",  "knowledge_area_links",   "knowledge_area_id"),
    ("material_types",    models.SharedPlatformMaterialType,  "material_type",   "material_type_links",    "material_type_id"),
    ("academic_programs", models.SharedPlatformAcademicProgram, "academic_program", "academic_program_links", "academic_program_id"),
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


class ValidSintaxisSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.ValidSintaxis
        fields = [*AUDIT_FIELDS, "name", "booleans", "parenthesis", "fields"]
        read_only_fields = AUDIT_FIELDS


class LinkCheckLogSerializer(serializers.ModelSerializer):

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


class PlatformSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Clave de API en texto plano; se almacenará cifrada.",
    )

    institutions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Institution.objects.all(), required=False, write_only=True,
    )
    languages = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Language.objects.all(), required=False, write_only=True,
    )
    countries = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Country.objects.all(), required=False, write_only=True,
    )
    knowledge_areas = serializers.PrimaryKeyRelatedField(
        many=True, queryset=KnowledgeArea.objects.all(), required=False, write_only=True,
    )
    material_types = serializers.PrimaryKeyRelatedField(
        many=True, queryset=MaterialType.objects.all(), required=False, write_only=True,
    )
    academic_programs = serializers.PrimaryKeyRelatedField(
        many=True, queryset=AcademicProgram.objects.all(), required=False, write_only=True,
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
        for data_field, _, _, manager_name, id_field in PLATFORM_RELATION_CONFIG:
            representation[data_field] = list(
                getattr(instance, manager_name).values_list(id_field, flat=True)
            )
        return representation

    def _sync_relation(self, platform, new_objects, through_model, relation_field):
        user = platform.updated_by or platform.created_by

        current_links = through_model.objects.filter(platform=platform)
        current_ids = set(current_links.values_list(f"{relation_field}_id", flat=True))
        new_ids = {obj.id for obj in new_objects}

        ids_to_remove = current_ids - new_ids
        ids_to_add = new_ids - current_ids

        if ids_to_remove:
            links_to_remove = current_links.filter(
                **{f"{relation_field}_id__in": ids_to_remove}
            )
            for link in links_to_remove:
                link.soft_delete(
                    user=user,
                    explanation="Relación eliminada durante la actualización de la plataforma.",
                )

        for obj in new_objects:
            if obj.id not in ids_to_add:
                continue

            lookup = {"platform": platform, relation_field: obj}
            archived_link = (
                through_model.all_objects
                .filter(deleted_at__isnull=False, **lookup)
                .first()
            )

            if archived_link:
                archived_link.restore()
                archived_link.updated_by = user
                archived_link.updated_at = timezone.now()
                archived_link.save(update_fields=["updated_by", "updated_at"])
            else:
                through_model.objects.create(
                    platform=platform,
                    **{relation_field: obj},
                    created_by=user,
                )

    def _sync_relations(self, platform, data):
        for data_field, through_model, relation_field, _, _ in PLATFORM_RELATION_CONFIG:
            if data_field in data:
                self._sync_relation(platform, data[data_field], through_model, relation_field)

    @transaction.atomic
    def create(self, validated_data):
        raw_api_key = validated_data.pop("api_key", None)

        relation_data = {}
        for data_field, *_ in PLATFORM_RELATION_CONFIG:
            if data_field in validated_data:
                relation_data[data_field] = validated_data.pop(data_field)

        platform = super().create(validated_data)

        if raw_api_key is not None:
            platform.set_api_key(raw_api_key)
            platform.save(update_fields=["encrypted_api_key"])

        if relation_data:
            self._sync_relations(platform, relation_data)

        return platform

    @transaction.atomic
    def update(self, instance, validated_data):
        raw_api_key = validated_data.pop("api_key", None)

        relation_data = {}
        for data_field, *_ in PLATFORM_RELATION_CONFIG:
            if data_field in validated_data:
                relation_data[data_field] = validated_data.pop(data_field)

        platform = super().update(instance, validated_data)

        if raw_api_key is not None:
            platform.set_api_key(raw_api_key)
            platform.save(update_fields=["encrypted_api_key"])

        if relation_data:
            self._sync_relations(platform, relation_data)

        return platform


class PlatformPublicSerializer(serializers.ModelSerializer):
    """
    Serializador de solo lectura para la exploración pública.
    No expone: encrypted_api_key, campos de auditoría interna ni datos de validación.
    """
    valid_sintaxis = ValidSintaxisSerializer(read_only=True)
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

    def get_institutions(self, obj):
        return list(
            Institution.objects.filter(platform_support_links__platform=obj).values("id", "name")
        )

    def get_languages(self, obj):
        return list(
            Language.objects.filter(platform_links__platform=obj).values("id", "name", "abbreviation")
        )

    def get_countries(self, obj):
        return list(
            Country.objects.filter(platform_links__platform=obj).values("id", "name", "abbreviation", "emoji_flag")
        )

    def get_knowledge_areas(self, obj):
        return list(
            KnowledgeArea.objects.filter(platform_links__platform=obj).values("id", "name")
        )

    def get_material_types(self, obj):
        return list(
            MaterialType.objects.filter(platform_links__platform=obj).values("id", "name")
        )

    def get_academic_programs(self, obj):
        return list(
            AcademicProgram.objects.filter(platform_links__platform=obj).values("id", "name")
        )

    def get_link_status(self, obj):
        latest_log = obj.link_check_logs.first()
        if latest_log:
            return {
                "is_active": latest_log.is_active,
                "last_check": latest_log.last_check,
            }

        return {
            "is_active": True,
            "last_check": None,
        }
