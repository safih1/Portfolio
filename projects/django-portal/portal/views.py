"""Views for the client portal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ClientForm, InvoiceForm, ProjectForm
from .models import Client, Invoice, Project

ACTIVE_STATUSES = [
    Project.Status.DISCOVERY,
    Project.Status.IN_PROGRESS,
    Project.Status.REVIEW,
]
OPEN_INVOICE_STATUSES = [Invoice.Status.SENT, Invoice.Status.OVERDUE]


def _money(value) -> Decimal:
    return value or Decimal("0")


def _next_invoice_number() -> str:
    prefix = f"INV-{timezone.localdate().year}-"
    numbers = Invoice.objects.filter(number__startswith=prefix).values_list(
        "number", flat=True
    )
    highest = 0
    for number in numbers:
        try:
            highest = max(highest, int(number.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{highest + 1:03d}"


def _render_form(
    request: HttpRequest,
    form,
    *,
    title: str,
    eyebrow: str,
    cancel_url: str,
) -> HttpResponse:
    return render(
        request,
        "portal/form.html",
        {
            "form": form,
            "title": title,
            "eyebrow": eyebrow,
            "cancel_url": cancel_url,
        },
    )


def dashboard(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    outstanding = _money(
        Invoice.objects.filter(status__in=OPEN_INVOICE_STATUSES).aggregate(
            total=Sum("amount")
        )["total"]
    )
    paid = _money(
        Invoice.objects.filter(status=Invoice.Status.PAID).aggregate(
            total=Sum("amount")
        )["total"]
    )
    context = {
        "stats": {
            "clients": Client.objects.count(),
            "active_projects": Project.objects.filter(
                status__in=ACTIVE_STATUSES
            ).count(),
            "outstanding": outstanding,
            "paid": paid,
        },
        "recent_projects": Project.objects.select_related("client").order_by(
            "-updated_at"
        )[:5],
        "open_invoices": Invoice.objects.select_related("client", "project")
        .filter(status__in=OPEN_INVOICE_STATUSES)
        .order_by("due_on")[:5],
        "today": today,
    }
    return render(request, "portal/dashboard.html", context)


def client_list(request: HttpRequest) -> HttpResponse:
    search = (request.GET.get("q") or "").strip()
    clients = Client.objects.annotate(project_count=Count("projects", distinct=True))
    if search:
        clients = clients.filter(
            Q(name__icontains=search)
            | Q(company__icontains=search)
            | Q(email__icontains=search)
        )
    clients = list(clients.order_by("name"))
    outstanding_by_client = {
        row["client"]: row["total"]
        for row in Invoice.objects.filter(status__in=OPEN_INVOICE_STATUSES)
        .values("client")
        .annotate(total=Sum("amount"))
    }
    for client in clients:
        client.outstanding = outstanding_by_client.get(client.pk, Decimal("0"))
    return render(
        request,
        "portal/client_list.html",
        {"clients": clients, "search": search},
    )


def client_detail(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(Client, pk=pk)
    projects = client.projects.all()
    invoices = client.invoices.select_related("project").all()
    context = {
        "client": client,
        "projects": projects,
        "invoices": invoices,
        "active_projects": projects.filter(status__in=ACTIVE_STATUSES).count(),
        "outstanding": _money(
            invoices.filter(status__in=OPEN_INVOICE_STATUSES).aggregate(
                total=Sum("amount")
            )["total"]
        ),
        "paid": _money(
            invoices.filter(status=Invoice.Status.PAID).aggregate(
                total=Sum("amount")
            )["total"]
        ),
    }
    return render(request, "portal/client_detail.html", context)


def client_create(request: HttpRequest) -> HttpResponse:
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"{client.name} added to the portal.")
        return redirect(client)
    return _render_form(
        request,
        form,
        title="New client",
        eyebrow="Clients",
        cancel_url=reverse("portal:client_list"),
    )


def project_list(request: HttpRequest) -> HttpResponse:
    status = (request.GET.get("status") or "").strip()
    projects = Project.objects.select_related("client")
    if status in Project.Status.values:
        projects = projects.filter(status=status)
    else:
        status = ""
    counts = {
        row["status"]: row["total"]
        for row in Project.objects.values("status").annotate(total=Count("id"))
    }
    return render(
        request,
        "portal/project_list.html",
        {
            "projects": projects,
            "status": status,
            "statuses": [
                (value, label, counts.get(value, 0))
                for value, label in Project.Status.choices
            ],
            "total": Project.objects.count(),
        },
    )


def project_detail(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(
        Project.objects.select_related("client"), pk=pk
    )
    return render(
        request,
        "portal/project_detail.html",
        {
            "project": project,
            "invoices": project.invoices.all(),
            "today": timezone.localdate(),
        },
    )


def project_create(request: HttpRequest) -> HttpResponse:
    initial = {}
    client_id = request.GET.get("client")
    if client_id:
        client = Client.objects.filter(pk=client_id).first()
        if client:
            initial["client"] = client
    form = ProjectForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Project “{project.name}” created.")
        return redirect(project)
    return _render_form(
        request,
        form,
        title="New project",
        eyebrow="Projects",
        cancel_url=reverse("portal:project_list"),
    )


@require_POST
def project_progress(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    try:
        progress = int(request.POST.get("progress", ""))
    except (TypeError, ValueError):
        progress = -1
    if progress < 0 or progress > 100:
        messages.error(request, "Progress must be between 0 and 100.")
    else:
        project.progress = progress
        project.save(update_fields=["progress", "updated_at"])
        messages.success(request, f"Progress updated to {progress}%.")
    return redirect(project)


def invoice_list(request: HttpRequest) -> HttpResponse:
    status = (request.GET.get("status") or "").strip()
    invoices = Invoice.objects.select_related("client", "project")
    today = timezone.localdate()
    if status == "overdue":
        invoices = invoices.filter(due_on__lt=today).exclude(
            status__in=[Invoice.Status.PAID, Invoice.Status.DRAFT]
        )
    elif status in Invoice.Status.values:
        invoices = invoices.filter(status=status)
    else:
        status = ""
    context = {
        "invoices": invoices,
        "status": status,
        "statuses": Invoice.Status.choices,
        "outstanding": _money(
            Invoice.objects.filter(status__in=OPEN_INVOICE_STATUSES).aggregate(
                total=Sum("amount")
            )["total"]
        ),
        "paid": _money(
            Invoice.objects.filter(status=Invoice.Status.PAID).aggregate(
                total=Sum("amount")
            )["total"]
        ),
        "today": today,
    }
    return render(request, "portal/invoice_list.html", context)


def invoice_create(request: HttpRequest) -> HttpResponse:
    initial = {
        "number": _next_invoice_number(),
        "issued_on": timezone.localdate(),
        "due_on": timezone.localdate() + timedelta(days=14),
        "status": Invoice.Status.SENT,
    }
    project_id = request.GET.get("project")
    if project_id:
        project = Project.objects.filter(pk=project_id).first()
        if project:
            initial.update(
                {
                    "client": project.client,
                    "project": project,
                    "amount": project.budget,
                }
            )
    else:
        client_id = request.GET.get("client")
        if client_id:
            client = Client.objects.filter(pk=client_id).first()
            if client:
                initial["client"] = client
    form = InvoiceForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        invoice = form.save()
        messages.success(request, f"Invoice {invoice.number} created.")
        return redirect("portal:invoice_list")
    return _render_form(
        request,
        form,
        title="New invoice",
        eyebrow="Invoices",
        cancel_url=reverse("portal:invoice_list"),
    )


@require_POST
def invoice_mark_paid(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.mark_paid()
    messages.success(request, f"Invoice {invoice.number} marked as paid.")
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)
    return redirect("portal:invoice_list")
