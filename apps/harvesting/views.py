from apps.core.viewsets import AuditableViewSet
from . import models, serializers

class ScheduleViewSet(AuditableViewSet):
    queryset = models.Schedule.objects.all()
    serializers_class = serializers.ScheduleSerializer
    search_fields = ["start_date"]
    ordering_fields = ["start_date"]

class HarvestViewSet(AuditableViewSet):
    queryset = models.Harvest.objects.all()
    serializers_class = serializers.HarvestSerializer
    search_fields = ["start_date"]
    ordering_fields = ["start_date"]
