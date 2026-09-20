from rest_framework import serializers

from apps.core.viewsets import ArchivedNameMixin

from . import models

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


class InstitutionSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.Institution
        fields = [*AUDIT_FIELDS, "name"]
        read_only_fields = AUDIT_FIELDS


class LanguageSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name", "abbreviation")

    class Meta:
        model = models.Language
        fields = [*AUDIT_FIELDS, "abbreviation", "name"]
        read_only_fields = AUDIT_FIELDS


class CountrySerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name", "abbreviation")

    class Meta:
        model = models.Country
        fields = [*AUDIT_FIELDS, "name", "abbreviation", "emoji_flag"]
        read_only_fields = AUDIT_FIELDS


class MaterialTypeSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.MaterialType
        fields = [*AUDIT_FIELDS, "name"]
        read_only_fields = AUDIT_FIELDS


class EditorialSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.Editorial
        fields = [*AUDIT_FIELDS, "name"]
        read_only_fields = AUDIT_FIELDS


class KnowledgeAreaSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.KnowledgeArea
        fields = [*AUDIT_FIELDS, "name"]
        read_only_fields = AUDIT_FIELDS


class AcademicProgramSerializer(ArchivedNameMixin, serializers.ModelSerializer):
    archived_unique_fields = ("name",)

    class Meta:
        model = models.AcademicProgram
        fields = [*AUDIT_FIELDS, "name"]
        read_only_fields = AUDIT_FIELDS


class SharedAcademicProgramKnowledgeAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SharedAcademicProgramKnowledgeArea
        fields = [*AUDIT_FIELDS, "knowledge_area", "academic_program"]
        read_only_fields = AUDIT_FIELDS
