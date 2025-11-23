from rest_framework import serializers
from .models import Lawyer, StatusOption, Person
from .models import UploadBatch, UploadRowStaging, BatchDiff


class LawyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lawyer
        fields = ["id", "sicil_no", "ad", "soyad", "created_at"]


class StatusOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusOption
        fields = ["id", "key", "label", "color"]


class PersonListSerializer(serializers.ModelSerializer):
    cevapDurumu = serializers.CharField(source='cevap_status.key', allow_null=True)

    class Meta:
        model = Person
        fields = ["id", "kisi_sicilno", "ad", "soyad", "mail", "ilce", "cevapDurumu"]


class UploadBatchSerializer(serializers.ModelSerializer):
    lawyerId = serializers.IntegerField(source='lawyer_id')

    class Meta:
        model = UploadBatch
        fields = ["id", "lawyerId", "original_filename", "file_path", "row_count", "status", "created_by", "created_at"]


class DiffResponseSerializer(serializers.Serializer):
    batchId = serializers.IntegerField()
    lawyer = serializers.DictField()
    added = serializers.ListField()
    removed = serializers.ListField()
    changed = serializers.ListField()
    counts = serializers.DictField()
