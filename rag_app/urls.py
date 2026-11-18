from django.urls import path
from .views import ask_api

urlpatterns = [
    path("ask/", ask_api, name="ask_api"),
]