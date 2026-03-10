from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

urlpatterns = [
    path("login", TokenObtainPairView.as_view(), name="token-obtain"),
    path("refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("me", views.me, name="auth-me"),
    path("users/", views.user_list_create, name="user-list-create"),
    path("users/<int:pk>/", views.user_detail, name="user-detail"),
]
