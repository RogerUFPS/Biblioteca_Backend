import django_filters  # type: ignore[import-untyped]

from . import models


class PlatformBaseFilter(django_filters.FilterSet):
    """Filtros relacionales y booleanos compartidos por Platform."""

    institution = django_filters.NumberFilter(method="filter_institution")
    country = django_filters.NumberFilter(method="filter_country")
    language = django_filters.NumberFilter(method="filter_language")
    knowledge_area = django_filters.NumberFilter(method="filter_knowledge_area")
    material_type = django_filters.NumberFilter(method="filter_material_type")
    academic_program = django_filters.NumberFilter(method="filter_academic_program")

    requires_registration = django_filters.BooleanFilter()
    has_access_text = django_filters.BooleanFilter()
    is_harvestable = django_filters.BooleanFilter()

    class Meta:
        model = models.Platform
        fields = []

    def filter_institution(self, queryset, name, value):
        return queryset.filter(
            support_links__institution_id=value,
            support_links__deleted_at__isnull=True,
            support_links__institution__deleted_at__isnull=True,
        ).distinct()

    def filter_country(self, queryset, name, value):
        return queryset.filter(
            country_links__country_id=value,
            country_links__deleted_at__isnull=True,
            country_links__country__deleted_at__isnull=True,
        ).distinct()

    def filter_language(self, queryset, name, value):
        return queryset.filter(
            language_links__language_id=value,
            language_links__deleted_at__isnull=True,
            language_links__language__deleted_at__isnull=True,
        ).distinct()

    def filter_knowledge_area(self, queryset, name, value):
        return queryset.filter(
            knowledge_area_links__knowledge_area_id=value,
            knowledge_area_links__deleted_at__isnull=True,
            knowledge_area_links__knowledge_area__deleted_at__isnull=True,
        ).distinct()

    def filter_material_type(self, queryset, name, value):
        return queryset.filter(
            material_type_links__material_type_id=value,
            material_type_links__deleted_at__isnull=True,
            material_type_links__material_type__deleted_at__isnull=True,
        ).distinct()

    def filter_academic_program(self, queryset, name, value):
        return queryset.filter(
            academic_program_links__academic_program_id=value,
            academic_program_links__deleted_at__isnull=True,
            academic_program_links__academic_program__deleted_at__isnull=True,
        ).distinct()


class PlatformFilter(PlatformBaseFilter):
    """Filtros del listado administrativo de plataformas."""

    status = django_filters.ChoiceFilter(
        choices=models.Platform.Status.choices,
    )
    valid_sintaxis = django_filters.NumberFilter(
        method="filter_valid_sintaxis",
    )

    class Meta:
        model = models.Platform
        fields = []

    def filter_valid_sintaxis(self, queryset, name, value):
        return queryset.filter(
            valid_sintaxis_id=value,
            valid_sintaxis__deleted_at__isnull=True,
        )


class PlatformPublicFilter(PlatformBaseFilter):
    """Filtros de la exploración pública de plataformas publicadas."""

    class Meta:
        model = models.Platform
        fields = []
