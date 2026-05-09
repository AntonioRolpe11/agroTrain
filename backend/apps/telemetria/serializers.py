from __future__ import annotations

from rest_framework import serializers


class PuntoSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()

    def validate(self, attrs):
        lat = attrs["lat"]
        lng = attrs["lng"]
        if not (27.0 <= lat <= 44.5 and -19.0 <= lng <= 5.0):
            raise serializers.ValidationError("El punto debe estar dentro del rango geográfico de España.")
        return attrs


class TelemetryExtractRequestSerializer(serializers.Serializer):
    features = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    punto = PuntoSerializer(required=False, allow_null=True)
    cloudThreshold = serializers.FloatField(required=False, default=20.0)
    startDate = serializers.DateField()
    endDate = serializers.DateField()

    def validate_cloudThreshold(self, value: float) -> float:
        if value < 0 or value > 100:
            raise serializers.ValidationError("cloudThreshold debe estar entre 0 y 100.")
        return value


class TelemetryPointSerializer(serializers.Serializer):
    date = serializers.CharField()
    values = serializers.DictField(child=serializers.FloatField())
    cloudCover = serializers.FloatField(required=False, allow_null=True)


class TelemetryExtractResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    collection = serializers.CharField(required=False, allow_null=True)
    indices = serializers.ListField(child=serializers.CharField(), required=False)
    startDate = serializers.CharField(required=False, allow_null=True)
    endDate = serializers.CharField(required=False, allow_null=True)
    imageCount = serializers.IntegerField(required=False)
    points = TelemetryPointSerializer(many=True, required=False)
