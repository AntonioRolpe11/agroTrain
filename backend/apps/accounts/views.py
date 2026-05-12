from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CustomUser
from .permissions import IsAdminRole
from .serializers import UserCreateSerializer, UserSerializer, UserUpdateSerializer


@extend_schema(responses={200: UserSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@extend_schema(
    request=UserCreateSerializer,
    responses={200: UserSerializer, 201: UserSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def user_list_create(request):
    if request.method == "GET":
        users = CustomUser.objects.all()
        return Response(UserSerializer(users, many=True).data)

    serializer = UserCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=UserUpdateSerializer,
    responses={200: UserSerializer},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def user_detail(request, pk: int):
    # Admin puede ver/editar cualquier usuario; técnico solo el suyo
    if not request.user.is_admin and request.user.pk != pk:
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

    user = get_object_or_404(CustomUser, pk=pk)

    if request.method == "GET":
        return Response(UserSerializer(user).data)

    if request.method == "DELETE":
        if not request.user.is_admin:
            return Response({"detail": "Solo administradores pueden eliminar usuarios."}, status=403)
        if user.pk == request.user.pk:
            return Response({"detail": "No puedes eliminar tu propia cuenta."}, status=400)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    partial = request.method == "PATCH"
    serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    if user.pk == request.user.pk and "is_active" in request.data:
        return Response({"detail": "No puedes desactivar tu propia cuenta."}, status=400)
    serializer.save()
    return Response(UserSerializer(user).data)
