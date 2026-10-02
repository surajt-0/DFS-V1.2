from django.contrib import admin

from .models import Case


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("case_number", "name", "investigator", "status", "priority", "created_at")
    list_filter = ("status", "priority", "is_demo")
    search_fields = ("case_number", "name", "subject_name", "tags")
