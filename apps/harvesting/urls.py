from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

router.register(
        "",
        views.ScheduleViewSet,
        basename="Schedule",
)

router.register(
        "",
        views.HarvestViewSet,
        basename="Harvest",
)

urlpatters = router.urls
