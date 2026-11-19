"""Admin forms. Validation errors from the services layer appear inline on the form."""

from django import forms

from . import services
from .models import Document, QAHistory


class DocumentAdminForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]

    def clean_file(self):
        file = self.cleaned_data["file"]
        # Only parse when a new file was uploaded (not when just the title changed).
        if "file" in self.changed_data:
            self._parsed = services.parse_docx_upload(file, exclude_pk=self.instance.pk)
        return file

    def save(self, commit=True):
        parsed = getattr(self, "_parsed", None)
        if parsed:
            services.apply_parsed_upload(self.instance, parsed)
        return super().save(commit)


class AskQuestionForm(forms.ModelForm):
    """The admin's "Add Q&A" page doubles as the question box.

    The answer is generated during validation, so if the LLM is down or there are no
    documents, the admin shows an error on the form and nothing is saved.
    """

    class Meta:
        model = QAHistory
        fields = ["question"]
        widgets = {"question": forms.Textarea(attrs={"rows": 3, "cols": 80})}

    def clean(self):
        cleaned = super().clean()
        question = (cleaned.get("question") or "").strip()
        if question:
            try:
                self._answer = services.answer_question(question)
            except services.QAError as exc:
                raise forms.ValidationError(str(exc)) from exc
            cleaned["question"] = question
        return cleaned

    def save(self, commit=True):
        services.apply_answer(self.instance, self._answer)
        return super().save(commit)
