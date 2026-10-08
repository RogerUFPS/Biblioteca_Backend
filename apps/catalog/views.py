from apps.core.viewsets import AuditableViewSet, get_acting_user

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

    def destroy(self, request, *args, **kwargs):
        area = self.get_object()
        program_ids = set(
            models.SharedAcademicProgramKnowledgeArea.objects.filter(
                knowledge_area=area,
            ).values_list("academic_program_id", flat=True)
        )
        response = super().destroy(request, *args, **kwargs)
        if response.status_code < 400 and program_ids:
            from apps.journal.classification import propagate_catalog_change
            propagate_catalog_change(program_ids, user=get_acting_user(request))
        return response

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        response = super().restore(request, pk=pk)
        if response.status_code < 400:
            program_ids = set(
                models.SharedAcademicProgramKnowledgeArea.objects.filter(
                    knowledge_area_id=pk,
                ).values_list("academic_program_id", flat=True)
            )
            from apps.journal.classification import propagate_catalog_change
            propagate_catalog_change(program_ids, user=get_acting_user(request))
        return response

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

    def destroy(self, request, *args, **kwargs):
        program = self.get_object()
        program_id = program.pk
        response = super().destroy(request, *args, **kwargs)
        if response.status_code < 400:
            from apps.journal.classification import propagate_catalog_change
            propagate_catalog_change([program_id], user=get_acting_user(request))
        return response

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        response = super().restore(request, pk=pk)
        if response.status_code < 400:
            from apps.journal.classification import propagate_catalog_change
            propagate_catalog_change([int(pk)], user=get_acting_user(request))
        return response

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
