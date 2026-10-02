from rest_framework import serializers

from .models import Case


class CaseListSerializer(serializers.ModelSerializer):
    investigator_name = serializers.CharField(source="investigator.get_full_name", read_only=True)
    investigator_username = serializers.CharField(source="investigator.username", read_only=True)
    evidence_count = serializers.ReadOnlyField()
    parsed_evidence_count = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = [
            "id", "case_number", "name", "status", "priority", "subject_name",
            "tags", "investigator_name", "investigator_username",
            "evidence_count", "parsed_evidence_count", "is_demo",
            "created_at", "updated_at", "closed_at",
        ]
        read_only_fields = fields


class EvidenceSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    evidence_type = serializers.CharField()
    evidence_type_display = serializers.CharField(source="get_evidence_type_display")
    original_filename = serializers.CharField()
    status = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display")
    row_count = serializers.IntegerField()
    size_bytes = serializers.IntegerField()
    uploaded_at = serializers.DateTimeField()


class CaseDetailSerializer(CaseListSerializer):
    tag_list = serializers.ReadOnlyField()
    can_edit = serializers.SerializerMethodField()
    can_upload_evidence = serializers.SerializerMethodField()
    evidence_items = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            "description", "tag_list", "can_edit", "can_upload_evidence", "evidence_items",
        ]

    def get_can_edit(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        from core.permissions import can_edit_case
        return can_edit_case(request.user, obj)

    def get_can_upload_evidence(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        from core.permissions import can_upload_evidence
        return can_upload_evidence(request.user, obj)

    def get_evidence_items(self, obj):
        items = obj.evidence_items.order_by("-uploaded_at")
        return EvidenceSummarySerializer(items, many=True).data


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ["name", "description", "status", "priority", "subject_name", "tags"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Case name is required.")
        return value
