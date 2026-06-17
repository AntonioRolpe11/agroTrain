from __future__ import annotations

from rest_framework import serializers

from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "email", "nombre", "role", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ["email", "nombre", "role", "password"]

    def create(self, validated_data):
        return CustomUser.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    # Opcional: si se envía, el administrador restablece la contraseña del usuario.
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = CustomUser
        fields = ["email", "nombre", "role", "is_active", "password"]

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
