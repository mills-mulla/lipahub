from django.urls import path

from . import views

app_name = "lipahub"
urlpatterns = [
    path("webhooks/<str:provider>/<str:token>/<uuid:correlation_id>/", views.webhook, name="webhook-cid"),
    path("webhooks/<str:provider>/<str:token>/", views.webhook, name="webhook"),
    path("inbound/<str:provider>/<str:token>/", views.inbound, name="inbound"),
    path("healthz/", views.healthz, name="healthz"),
]