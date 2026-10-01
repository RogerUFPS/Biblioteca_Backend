from django.db import transaction
from rest_framework import serializers

from drf_spectacular.utils import extend_schema_field

from apps.catalog.models import (
    AcademicProgram,
    Country,
    KnowledgeArea,
    Language,
    MaterialType,
)
from apps.core.serializers import (
    RelationConfig,
    SoftDeleteRelationSyncMixin,
)
from apps.core.viewsets import ArchivedNameMixin
from apps.platforms.models import Platform

from . import models


JOURNAL_RELATION_CONFIG = (
    RelationConfig(
        data_field="languages",
        through_model=models.SharedJournalLanguage,
        relation_field="language",
    ),
    RelationConfig(
        data_field="countries",
        through_model=models.SharedJournalCountry,
        relation_field="country",
    ),
    RelationConfig(
        data_field="knowledge_areas",
        through_model=models.SharedJournalKnowledgeArea,
        relation_field="knowledge_area",
    ),
    RelationConfig(
        data_field="material_types",
        through_model=models.SharedJournalMaterialType,
        relation_field="material_type",
    ),
    RelationConfig(
        data_field="academic_programs",
        through_model=models.SharedJournalAcademicProgram,
        relation_field="academic_program",
    ),
    RelationConfig(
        data_field="platforms",
        through_model=models.SharedJournalPlatform,
        relation_field="platform",
        extra_fields=(
            "start_period",
            "finish_period",
            "has_full_text",
        ),
        ordering=("platform__name",),
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


def _normalize_issn(value: str) -> str:
    """
    Normaliza el ISSN al formato XXXX-XXXX.

    Admite como entrada el ISSN con o sin guion.
    """

    if not value or not value.strip():
        raise serializers.ValidationError(
            "El ISSN es obligatorio."
        )

    compact_issn = (
        "".join(value.split())
        .replace("-", "")
        .upper()
    )

    if (
        len(compact_issn) != 8
        or not compact_issn[:7].isdigit()
        or not (
            compact_issn[7].isdigit()
            or compact_issn[7] == "X"
        )
    ):
        raise serializers.ValidationError(
            "El ISSN debe tener el formato XXXX-XXXX."
        )

    return (
        f"{compact_issn[:4]}-"
        f"{compact_issn[4:]}"
    )


def _validate_period(
    start_period,
    finish_period,
    *,
    field_name="finish_period",
):
    """
    Valida que el período final no sea anterior
    al período inicial.
    """

    if (
        start_period
        and finish_period
        and finish_period < start_period
    ):
        raise serializers.ValidationError(
            {
                field_name: (
                    "El período final no puede ser anterior "
                    "al período inicial."
                )
            }
        )


class JournalPlatformRelationSerializer(
    serializers.Serializer
):
    """
    Datos específicos de la relación entre una revista
    y una plataforma.
    """

    platform = serializers.PrimaryKeyRelatedField(
        queryset=Platform.objects.all(),
    )

    start_period = serializers.DateField(
        required=False,
        allow_null=True,
    )

    finish_period = serializers.DateField(
        required=False,
        allow_null=True,
    )

    has_full_text = serializers.BooleanField(
        required=False,
    )

    def validate(self, attrs):
        _validate_period(
            attrs.get("start_period"),
            attrs.get("finish_period"),
        )

        return attrs


class JournalSerializer(
    SoftDeleteRelationSyncMixin,
    ArchivedNameMixin,
    serializers.ModelSerializer,
):
    """
    Serializador administrativo de revistas.

    La identificación y deduplicación se realiza mediante ISSN.

    Todas las relaciones mediante tablas intermedias se sincronizan
    mediante SoftDeleteRelationSyncMixin.

    La relación con plataformas utiliza el mismo mecanismo genérico,
    incluyendo sus atributos adicionales:
    start_period, finish_period y has_full_text.
    """

    archived_unique_fields = ("issn",)

    relation_config = JOURNAL_RELATION_CONFIG
    relation_parent_field = "journal"

    relation_delete_explanation = (
        "Relación eliminada durante "
        "la actualización de la revista."
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

    platforms = JournalPlatformRelationSerializer(
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = models.Journal

        fields = [
            *AUDIT_FIELDS,
            "issn",
            "title",
            "editorial",
            "license",
            "url_image",
            "has_apc",
            "active",
            "start_period",
            "finish_period",
            "validated_by",
            "validated_at",
            "fetched_at",
            "languages",
            "countries",
            "knowledge_areas",
            "material_types",
            "academic_programs",
            "platforms",
        ]

        read_only_fields = [
            *AUDIT_FIELDS,
            "active",
            "validated_by",
            "validated_at",
            "fetched_at",
        ]

    def validate_issn(self, value):
        """
        Normaliza el ISSN para garantizar una representación
        consistente y permitir una deduplicación correcta.
        """
        return _normalize_issn(value)

    def validate(self, attrs):
        """
        Valida los datos generales de la revista.

        En actualizaciones parciales se utilizan los valores
        existentes cuando alguno de los períodos no fue enviado.

        Cuando se está restaurando automáticamente una revista
        archivada, también se consideran sus valores anteriores.
        """
        attrs = super().validate(attrs)

        base_instance = (
            self.instance
            or getattr(
                self,
                "_archived_instance",
                None,
            )
        )

        start_period = attrs.get(
            "start_period",
            getattr(
                base_instance,
                "start_period",
                None,
            ),
        )

        finish_period = attrs.get(
            "finish_period",
            getattr(
                base_instance,
                "finish_period",
                None,
            ),
        )

        _validate_period(
            start_period,
            finish_period,
        )

        self._validate_platform_periods(
            attrs.get("platforms")
        )

        return attrs

    def validate_platforms(self, value):
        """
        Valida que una plataforma no aparezca más de una vez.
        """
        platform_ids = [
            item["platform"].pk
            for item in value
        ]

        if len(platform_ids) != len(set(platform_ids)):
            raise serializers.ValidationError(
                "Una plataforma no puede aparecer más de una vez."
            )

        return value

    def _validate_platform_periods(self, platform_data):
        """
        Valida los períodos efectivos de las relaciones Journal
        <-> Platform.

        En una actualización parcial, si solo se envía uno de los
        períodos, el otro se obtiene de la relación existente.

        También funciona cuando una revista archivada está siendo
        restaurada, utilizando su relación archivada como referencia.
        """
        if not platform_data:
            return

        base_instance = (
            self.instance
            or getattr(
                self,
                "_archived_instance",
                None,
            )
        )

        if base_instance is None:
            return

        existing_links = {
            link.platform_id: link
            for link in (
                models.SharedJournalPlatform.all_objects
                .filter(journal=base_instance)
            )
        }

        errors = []

        for item in platform_data:
            platform_id = item["platform"].pk
            existing_link = existing_links.get(platform_id)

            effective_start = item.get(
                "start_period",
                getattr(
                    existing_link,
                    "start_period",
                    None,
                ),
            )

            effective_finish = item.get(
                "finish_period",
                getattr(
                    existing_link,
                    "finish_period",
                    None,
                ),
            )

            try:
                _validate_period(
                    effective_start,
                    effective_finish,
                )
            except serializers.ValidationError as exc:
                errors.append(
                    {
                        "platform": platform_id,
                        "detail": exc.detail,
                    }
                )

        if errors:
            raise serializers.ValidationError(
                {
                    "platforms": errors,
                }
            )

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        return self._represent_relations(
            instance=instance,
            representation=representation,
        )

    def _clear_validation(self, journal):
        """
        Una ficha modificada debe ser validada nuevamente
        antes de regresar a la consulta pública.
        """
        if (
            journal.validated_by_id is None
            and journal.validated_at is None
        ):
            return

        journal.validated_by = None
        journal.validated_at = None

        journal.save(
            update_fields=[
                "validated_by",
                "validated_at",
            ]
        )

    @transaction.atomic
    def create(self, validated_data):
        relation_data = self._extract_relation_data(
            validated_data
        )

        journal = super().create(
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
            self._clear_validation(journal)

        if relation_data:
            self._sync_relations(
                parent=journal,
                relation_data=relation_data,
            )

        return journal

    @transaction.atomic
    def update(
        self,
        instance,
        validated_data,
    ):
        relation_data = self._extract_relation_data(
            validated_data
        )

        journal = super().update(
            instance,
            validated_data,
        )

        if relation_data:
            self._sync_relations(
                parent=journal,
                relation_data=relation_data,
            )

        self._clear_validation(journal)

        return journal


# ==============================================================================
# ESQUEMAS DE RESPUESTA PÚBLICA PARA SWAGGER
# ==============================================================================


class JournalPublicLanguageSchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    abbreviation = serializers.CharField()


class JournalPublicCountrySchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    abbreviation = serializers.CharField()
    emoji_flag = serializers.CharField(
        allow_blank=True,
        allow_null=True,
    )


class JournalPublicKnowledgeAreaSchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class JournalPublicMaterialTypeSchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class JournalPublicAcademicProgramSchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()


class JournalPublicPlatformSchemaSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    base_api_url = serializers.URLField(
        allow_blank=True,
        allow_null=True,
    )
    start_period = serializers.DateField(
        allow_null=True,
    )
    finish_period = serializers.DateField(
        allow_null=True,
    )
    has_full_text = serializers.BooleanField()


class JournalPublicSerializer(
    serializers.ModelSerializer
):
    """
    Serializador de solo lectura para la exploración pública.

    No expone campos internos de auditoría ni validación.
    """

    editorial_name = serializers.CharField(
        source="editorial.name",
        read_only=True,
        default=None,
    )

    languages = (
        serializers.SerializerMethodField()
    )

    countries = (
        serializers.SerializerMethodField()
    )

    knowledge_areas = (
        serializers.SerializerMethodField()
    )

    material_types = (
        serializers.SerializerMethodField()
    )

    academic_programs = (
        serializers.SerializerMethodField()
    )

    platforms = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = models.Journal

        fields = [
            "id",
            "issn",
            "title",
            "editorial_name",
            "license",
            "url_image",
            "has_apc",
            "active",
            "start_period",
            "finish_period",
            "languages",
            "countries",
            "knowledge_areas",
            "material_types",
            "academic_programs",
            "platforms",
        ]

    @extend_schema_field(
        JournalPublicLanguageSchemaSerializer(many=True)
    )
    def get_languages(self, obj):
        return list(
            Language.objects.filter(
                journal_links__journal=obj,
                journal_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
                "abbreviation",
            )
        )

    @extend_schema_field(
        JournalPublicCountrySchemaSerializer(many=True)
    )
    def get_countries(self, obj):
        return list(
            Country.objects.filter(
                journal_links__journal=obj,
                journal_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
                "abbreviation",
                "emoji_flag",
            )
        )

    @extend_schema_field(
        JournalPublicKnowledgeAreaSchemaSerializer(many=True)
    )
    def get_knowledge_areas(self, obj):
        return list(
            KnowledgeArea.objects.filter(
                journal_links__journal=obj,
                journal_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        JournalPublicMaterialTypeSchemaSerializer(many=True)
    )
    def get_material_types(self, obj):
        return list(
            MaterialType.objects.filter(
                journal_links__journal=obj,
                journal_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        JournalPublicAcademicProgramSchemaSerializer(many=True)
    )
    def get_academic_programs(self, obj):
        return list(
            AcademicProgram.objects.filter(
                journal_links__journal=obj,
                journal_links__deleted_at__isnull=True,
            ).values(
                "id",
                "name",
            )
        )

    @extend_schema_field(
        JournalPublicPlatformSchemaSerializer(many=True)
    )
    def get_platforms(self, obj):
        links = (
            models.SharedJournalPlatform.objects
            .filter(
                journal=obj,
                platform__deleted_at__isnull=True,
                platform__status=(
                    Platform.Status.PUBLICADO
                ),
            )
            .select_related(
                "platform"
            )
            .order_by(
                "platform__name"
            )
        )

        return [
            {
                "id": link.platform_id,
                "name": link.platform.name,
                "base_api_url": (
                    link.platform.base_api_url
                ),
                "start_period": (
                    link.start_period
                ),
                "finish_period": (
                    link.finish_period
                ),
                "has_full_text": (
                    link.has_full_text
                ),
            }
            for link in links
        ]