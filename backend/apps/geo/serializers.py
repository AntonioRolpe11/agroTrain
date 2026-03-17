from __future__ import annotations

from rest_framework import serializers


class ProvinciaOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    nombre = serializers.CharField()


class MunicipioOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    nombre = serializers.CharField()
    provinciaId = serializers.CharField()


class MunicipioViewportResponseSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    bbox = serializers.ListField(child=serializers.FloatField(), required=False, allow_null=True)
    centroid = serializers.ListField(child=serializers.FloatField(), required=False, allow_null=True)
    source = serializers.CharField(required=False, allow_null=True)


