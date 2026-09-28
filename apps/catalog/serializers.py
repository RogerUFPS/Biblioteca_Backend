from django.db import transaction
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
    knowledge_areas = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=models.KnowledgeArea.objects.all(),
        required=True,
        allow_empty=False,
        write_only=True,
    )

    class Meta:
        model = models.AcademicProgram
        fields = [*AUDIT_FIELDS, "name", "knowledge_areas"]
        read_only_fields = AUDIT_FIELDS

    def validate_knowledge_areas(self, value):
        if len({area.pk for area in value}) != len(value):
            raise serializers.ValidationError(
                "No se puede repetir un área de conocimiento."
            )
        return value

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["knowledge_areas"] = list(
            instance.knowledge_area_links.values_list("knowledge_area_id", flat=True)
        )
        return representation

    @transaction.atomic
    def create(self, validated_data):
        knowledge_areas = validated_data.pop("knowledge_areas")
        program = super().create(validated_data)
        models.SharedAcademicProgramKnowledgeArea.objects.bulk_create(
            [
                models.SharedAcademicProgramKnowledgeArea(
                    academic_program=program,
                    knowledge_area=knowledge_area,
                    created_by=program.created_by,
                )
                for knowledge_area in knowledge_areas
            ]
        )
        return program

    @transaction.atomic
    def update(self, instance, validated_data):
        knowledge_areas = validated_data.pop("knowledge_areas", None)
        program = super().update(instance, validated_data)
        if knowledge_areas is not None:
            models.SharedAcademicProgramKnowledgeArea.objects.filter(
                academic_program=program,
            ).delete()
            models.SharedAcademicProgramKnowledgeArea.objects.bulk_create(
                [
                    models.SharedAcademicProgramKnowledgeArea(
                        academic_program=program,
                        knowledge_area=knowledge_area,
                        created_by=program.created_by,
                    )
                    for knowledge_area in knowledge_areas
                ]
            )
        return program
