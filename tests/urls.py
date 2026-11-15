from django.urls import path
from django.urls import include
urlpatterns = [path("lipahub/", include("src.lipahub.api.urls"))]