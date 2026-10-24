from django.urls import path

from .api.locations import DepartmentView, MunicipalityView
from .views import LiveView, ReadyView

urlpatterns = [
    path("locations/departments", DepartmentView.as_view(), name="departments"),
    path(
        "locations/departments/<str:code>/municipalities",
        MunicipalityView.as_view(),
        name="municipalities",
    ),
    path("health/live", LiveView.as_view(), name="health-live"),
    path("health/ready", ReadyView.as_view(), name="health-ready"),
]
