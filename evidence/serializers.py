from rest_framework import serializers

from .models import EvidenceItem


class EvidenceItemSerializer(serializers.ModelSerializer):
    evidence_type_display = serializers.CharField(source="get_evidence_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    artifact_kind = serializers.ReadOnlyField()
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)

    class Meta:
        model = EvidenceItem
        fields = [
            "id", "case_id", "evidence_type", "evidence_type_display", "original_filename",
            "sha256", "size_bytes", "note", "status", "status_display", "parse_error",
            "row_count", "uploaded_by_username", "uploaded_at", "parsed_at",
            "artifact_kind",
        ]
        read_only_fields = fields


class EvidenceUploadSerializer(serializers.Serializer):
    # Optional now: when omitted, EvidenceUploadAPI auto-detects the type
    # from the file itself (core.parsers.detect) instead of requiring the
    # examiner to classify every file by hand before uploading.
    evidence_type = serializers.ChoiceField(choices=EvidenceItem.EvidenceType.choices, required=False)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)
    file = serializers.FileField()

    def validate_file(self, value):
        max_bytes = 512 * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError("File exceeds the 512MB upload limit for this deployment.")
        return value
