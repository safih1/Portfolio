"""URL routes for the client portal."""

from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path(
        "projects/<int:pk>/progress/",
        views.project_progress,
        name="project_progress",
    ),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path(
        "invoices/<int:pk>/paid/",
        views.invoice_mark_paid,
        name="invoice_mark_paid",
    ),
]
