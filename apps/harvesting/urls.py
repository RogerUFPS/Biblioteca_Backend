from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

router.register(
    r"schedules",
    views.ScheduleViewSet,
    basename="schedule",
)

router.register(
    r"harvests",
    views.HarvestViewSet,
    basename="harvest",
)

urlpatterns = router.urls
