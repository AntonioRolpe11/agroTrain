from __future__ import annotations

from rest_framework import serializers


class MetricsSerializer(serializers.Serializer):
    mae = serializers.FloatField()
    rmse = serializers.FloatField()
    r2 = serializers.FloatField()


class TrainStartResponseSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    status = serializers.CharField()


class TrainingStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    phase = serializers.CharField(required=False, allow_null=True)
    algorithm = serializers.CharField(required=False, allow_null=True)
    current_epoch = serializers.IntegerField(required=False, allow_null=True)
    total_epochs = serializers.IntegerField(required=False, allow_null=True)
    current_target = serializers.CharField(required=False, allow_null=True)
    val_loss = serializers.FloatField(required=False, allow_null=True)
    n_train = serializers.IntegerField(required=False, allow_null=True)
    n_val = serializers.IntegerField(required=False, allow_null=True)
    metrics = serializers.DictField(child=MetricsSerializer(), required=False)
    warnings = serializers.ListField(child=serializers.CharField(), required=False)
    detail = serializers.CharField(required=False, allow_null=True)


class ModelMetadataSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    algorithm = serializers.CharField()
    crop = serializers.CharField()
    features = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    geo = serializers.DictField(required=False, default=dict)
    all_cols = serializers.ListField(child=serializers.CharField())
    targets = serializers.ListField(child=serializers.CharField())
    input_features = serializers.ListField(child=serializers.CharField())
    window_size = serializers.IntegerField()
    n_samples = serializers.IntegerField()
    n_train = serializers.IntegerField()
    n_val = serializers.IntegerField()
    metrics = serializers.DictField(child=MetricsSerializer())
    warnings = serializers.ListField(child=serializers.CharField())
    imported = serializers.BooleanField(required=False, default=False)
    created_at = serializers.CharField(required=False)


class ModelListResponseSerializer(serializers.Serializer):
    models = ModelMetadataSerializer(many=True)


class PredictionResponseSerializer(serializers.Serializer):
    prediction_id = serializers.IntegerField()
    model_id = serializers.CharField()
    generated_at = serializers.CharField()
    predicted_for_date = serializers.DateField()
    predictions = serializers.DictField(child=serializers.FloatField())
    input_row_count = serializers.IntegerField()
    warnings = serializers.ListField(child=serializers.CharField())


class PredictionHistoryResponseSerializer(serializers.Serializer):
    predictions = PredictionResponseSerializer(many=True)
