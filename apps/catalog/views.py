from apps.core.viewsets import AuditableViewSet

from . import models, serializers
from rest_framework.decorators import action
from rest_framework.response import Response


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

    @action(detail=True, methods=["get"], url_path="academic-programs")
    def academic_programs(self, request, pk=None):
        area = self.get_object()
        queryset = models.AcademicProgram.objects.filter(
            knowledge_area_links__knowledge_area=area,
        )
        queryset = self.filter_queryset(queryset)
        page = self.paginate_queryset(queryset)
        serializer = serializers.AcademicProgramSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class AcademicProgramViewSet(AuditableViewSet):
    queryset = models.AcademicProgram.objects.all()
    serializer_class = serializers.AcademicProgramSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    @action(detail=True, methods=["get"], url_path="knowledge-areas")
    def knowledge_areas(self, request, pk=None):
        program = self.get_object()
        queryset = models.KnowledgeArea.objects.filter(
            program_links__academic_program=program,
        )
        queryset = self.filter_queryset(queryset)
        page = self.paginate_queryset(queryset)
        serializer = serializers.KnowledgeAreaSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
