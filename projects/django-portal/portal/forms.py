"""Forms for creating and editing portal records."""

from __future__ import annotations

from django import forms

from .models import Client, Invoice, Project


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "company", "email", "phone", "website", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Context, preferences, history…"}),
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "client",
            "name",
            "status",
            "budget",
            "progress",
            "start_date",
            "due_date",
            "description",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(
                attrs={"rows": 5, "placeholder": "Scope, deliverables, and notes…"}
            ),
        }


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "client",
            "project",
            "number",
            "amount",
            "status",
            "issued_on",
            "due_on",
            "notes",
        ]
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "due_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Payment terms or a short note…"}
            ),
        }
