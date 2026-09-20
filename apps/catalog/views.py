from apps.core.viewsets import AuditableViewSet

from . import models, serializers
from .filters import SharedAcademicProgramKnowledgeAreaFilter


class InstitutionViewSet(AuditableViewSet):
    queryset = models.Institution.objects.all()
    serializer_class = serializers.InstitutionSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class LanguageViewSet(AuditableViewSet):
    queryset = models.Language.objects.all()
    serializer_class = serializers.LanguageSerializer
    search_fields = ["name", "abbreviation"]
    ordering_fields = ["name", "abbreviation", "created_at"]


class CountryViewSet(AuditableViewSet):
    queryset = models.Country.objects.all()
    serializer_class = serializers.CountrySerializer
    search_fields = ["name", "abbreviation"]
    ordering_fields = ["name", "abbreviation", "created_at"]


class MaterialTypeViewSet(AuditableViewSet):
    queryset = models.MaterialType.objects.all()
    serializer_class = serializers.MaterialTypeSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class EditorialViewSet(AuditableViewSet):
    queryset = models.Editorial.objects.all()
    serializer_class = serializers.EditorialSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class KnowledgeAreaViewSet(AuditableViewSet):
    queryset = models.KnowledgeArea.objects.all()
    serializer_class = serializers.KnowledgeAreaSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class AcademicProgramViewSet(AuditableViewSet):
    queryset = models.AcademicProgram.objects.all()
    serializer_class = serializers.AcademicProgramSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class SharedAcademicProgramKnowledgeAreaViewSet(AuditableViewSet):
    queryset = models.SharedAcademicProgramKnowledgeArea.objects.select_related(
        "knowledge_area",
        "academic_program",
    )
    serializer_class = serializers.SharedAcademicProgramKnowledgeAreaSerializer
    filterset_class = SharedAcademicProgramKnowledgeAreaFilter
