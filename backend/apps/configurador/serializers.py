from __future__ import annotations

from rest_framework import serializers

from .models import Configuracion, UVLVersion


class UVLVersionListSerializer(serializers.ModelSerializer):
    author_username = serializers.SerializerMethodField()

    class Meta:
        model = UVLVersion
        fields = [
            "id", "name", "description", "file_hash",
            "author_username", "created_at", "is_active", "is_valid", "validation_errors",
        ]

    def get_author_username(self, obj):
        return obj.author.nombre if obj.author else None


class UVLVersionDetailSerializer(UVLVersionListSerializer):
    tree = serializers.SerializerMethodField()

    class Meta(UVLVersionListSerializer.Meta):
        fields = UVLVersionListSerializer.Meta.fields + ["tree"]

    def get_tree(self, obj):
        from django.conf import settings
        from pathlib import Path
        from apps.configurador.services.flamapy_service import FlamapyService, _temp_uvl_file
        try:
            from flamapy.metamodels.bdd_metamodel.transformations import FmToBDD
            from flamapy.metamodels.fm_metamodel.transformations import UVLReader
        except ImportError:
            return None

        uvl_path = Path(settings.UVL_VERSIONS_PATH) / obj.file_path
        try:
            with _temp_uvl_file(uvl_path.read_text(encoding="utf-8")) as tmp:
                fm = UVLReader(str(tmp)).transform()
                # Temporarily swap class state to serialise this version's tree
                with FlamapyService._state_lock:
                    old_fm = FlamapyService._base_fm_model
                    old_bdd = FlamapyService._base_bdd_model
                    try:
                        FlamapyService._base_fm_model = fm
                        FlamapyService._base_bdd_model = FmToBDD(fm).transform()
                        return FlamapyService.to_dict()
                    finally:
                        FlamapyService._base_fm_model = old_fm
                        FlamapyService._base_bdd_model = old_bdd
        except Exception:
            return None


class CreateUVLVersionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    tree = serializers.JSONField()
    constraints_text = serializers.CharField(allow_blank=True, default="")


class ValidateUVLSerializer(serializers.Serializer):
    tree = serializers.JSONField()
    constraints_text = serializers.CharField(allow_blank=True, default="")


class ActivateUVLVersionSerializer(serializers.Serializer):
    confirm_incompatible = serializers.BooleanField(default=False)


class ConfiguracionSerializer(serializers.ModelSerializer):
    uvl_version_name = serializers.SerializerMethodField()
    uvl_version_active = serializers.SerializerMethodField()

    class Meta:
        model = Configuracion
        fields = [
            "id", "nombre", "features", "geo",
            "uvl_version", "uvl_version_name", "uvl_version_active",
            "is_obsolete", "obsolete_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_obsolete", "obsolete_reason", "created_at", "updated_at"]

    def get_uvl_version_name(self, obj):
        return obj.uvl_version.name if obj.uvl_version else None

    def get_uvl_version_active(self, obj):
        return obj.uvl_version.is_active if obj.uvl_version else False


class ValidateResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())


PARTIAL_STEP_CHOICES = ["parcel", "sensors", "telemetry", "objective", "full"]


class ValidateFeaturesRequestSerializer(serializers.Serializer):
    features = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    is_full = serializers.BooleanField(default=False)
    step = serializers.ChoiceField(choices=PARTIAL_STEP_CHOICES, default="full")


class UVLRequestSerializer(serializers.Serializer):
    uvl = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class SatisfiableResponseSerializer(serializers.Serializer):
    satisfiable = serializers.BooleanField()


class ConfigurationsNumberResponseSerializer(serializers.Serializer):
    configurationsNumber = serializers.IntegerField()


class DeadFeaturesResponseSerializer(serializers.Serializer):
    deadFeatures = serializers.ListField(child=serializers.CharField())
