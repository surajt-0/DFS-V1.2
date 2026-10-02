from django import forms

from .models import EvidenceItem

MAX_NOTE_LEN = 300


class EvidenceUploadForm(forms.ModelForm):
    file = forms.FileField(help_text="Upload the raw artefact file exactly as found on the source device.")

    class Meta:
        model = EvidenceItem
        fields = ["evidence_type", "note"]

    def clean_file(self):
        f = self.cleaned_data["file"]
        max_bytes = 512 * 1024 * 1024
        if f.size > max_bytes:
            raise forms.ValidationError("File exceeds the 512MB upload limit for this deployment.")
        return f

    def clean(self):
        cleaned = super().clean()
        etype = cleaned.get("evidence_type")
        f = cleaned.get("file")
        if etype and f:
            name = f.name.lower()
            expectations = {
                EvidenceItem.EvidenceType.CHROMIUM_HISTORY: None,   # "History" has no extension
                EvidenceItem.EvidenceType.CHROMIUM_LOGINS: None,    # "Login Data"
                EvidenceItem.EvidenceType.CHROMIUM_COOKIES: None,   # "Cookies"
                EvidenceItem.EvidenceType.CHROMIUM_DOWNLOADS: None,
                EvidenceItem.EvidenceType.FIREFOX_HISTORY: ".sqlite",
                EvidenceItem.EvidenceType.FIREFOX_COOKIES: ".sqlite",
                EvidenceItem.EvidenceType.FIREFOX_LOGINS: ".json",
                EvidenceItem.EvidenceType.SAFARI_HISTORY: ".db",
                EvidenceItem.EvidenceType.CACHE_ARCHIVE: ".zip",
            }
            expected = expectations.get(etype)
            if expected and not name.endswith(expected):
                self.add_error(
                    "file",
                    f"Selected artefact type usually expects a '{expected}' file. "
                    "Double-check you picked the right evidence type before continuing."
                )
        return cleaned
