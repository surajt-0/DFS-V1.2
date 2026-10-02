from rest_framework import serializers

from .models import AuditLogEntry


class AuditLogEntrySerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    case_number = serializers.CharField(source="case.case_number", read_only=True)

    class Meta:
        model = AuditLogEntry
        fields = ["id", "timestamp", "username", "action", "detail", "case_number", "ip_address", "path"]
        read_only_fields = fields

    def get_username(self, obj):
        return obj.username_snapshot or (obj.user.username if obj.user else "—")
