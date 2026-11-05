"""Admin configuration for the client portal."""

from django.contrib import admin

from .models import Client, Invoice, Project


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "created_at")
    search_fields = ("name", "company", "email")
    ordering = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "client",
        "status",
        "progress",
        "budget",
        "due_date",
        "is_overdue",
        "updated_at",
    )
    list_filter = ("status", "client")
    search_fields = ("name", "client__name", "client__company")
    date_hierarchy = "created_at"
    list_select_related = ("client",)

    @admin.display(boolean=True, description="Overdue")
    def is_overdue(self, obj: Project) -> bool:
        return obj.is_overdue


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "client",
        "project",
        "amount",
        "status",
        "due_on",
        "paid_on",
        "is_overdue",
    )
    list_filter = ("status", "issued_on", "due_on")
    search_fields = ("number", "client__name", "client__company")
    date_hierarchy = "issued_on"
    list_select_related = ("client", "project")
    actions = ("mark_paid",)

    @admin.display(boolean=True, description="Overdue")
    def is_overdue(self, obj: Invoice) -> bool:
        return obj.is_overdue

    @admin.action(description="Mark selected invoices as paid")
    def mark_paid(self, request, queryset):
        updated = 0
        for invoice in queryset.exclude(status=Invoice.Status.PAID):
            invoice.mark_paid()
            updated += 1
        self.message_user(request, f"{updated} invoice(s) marked as paid.")
