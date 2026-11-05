"""Tests for the client portal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Client, Invoice, Project


class PortalTestMixin:
    def setUp(self):
        self.today = timezone.localdate()
        self.client_record = Client.objects.create(
            name="Ada Lovelace",
            company="Analytical Engines",
            email="ada@example.com",
            phone="+1 555 0100",
            website="https://example.com",
        )
        self.project = Project.objects.create(
            client=self.client_record,
            name="Onboarding automation",
            status=Project.Status.IN_PROGRESS,
            budget=Decimal("2500.00"),
            progress=40,
            start_date=self.today - timedelta(days=10),
            due_date=self.today + timedelta(days=10),
        )
        self.invoice = Invoice.objects.create(
            client=self.client_record,
            project=self.project,
            number="INV-TEST-001",
            amount=Decimal("1250.00"),
            status=Invoice.Status.SENT,
            issued_on=self.today - timedelta(days=7),
            due_on=self.today + timedelta(days=7),
        )


class ModelTests(PortalTestMixin, TestCase):
    def test_client_str_prefers_company(self):
        self.assertEqual(str(self.client_record), "Analytical Engines")

    def test_project_status_tone(self):
        self.assertEqual(self.project.status_tone, "active")
        self.project.status = Project.Status.DELIVERED
        self.assertEqual(self.project.status_tone, "success")

    def test_project_overdue(self):
        self.assertFalse(self.project.is_overdue)
        self.project.due_date = self.today - timedelta(days=1)
        self.assertTrue(self.project.is_overdue)
        self.project.status = Project.Status.DELIVERED
        self.assertFalse(self.project.is_overdue)

    def test_invoice_overdue_ignores_drafts_and_paid(self):
        self.invoice.due_on = self.today - timedelta(days=2)
        self.invoice.status = Invoice.Status.SENT
        self.assertTrue(self.invoice.is_overdue)
        self.assertEqual(self.invoice.display_status, "overdue")
        self.assertEqual(self.invoice.status_tone, "danger")

        self.invoice.status = Invoice.Status.DRAFT
        self.assertFalse(self.invoice.is_overdue)

        self.invoice.status = Invoice.Status.PAID
        self.assertFalse(self.invoice.is_overdue)

    def test_invoice_mark_paid(self):
        self.invoice.mark_paid()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.paid_on, self.today)


class DashboardViewTests(PortalTestMixin, TestCase):
    def test_dashboard_totals(self):
        response = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["clients"], 1)
        self.assertEqual(response.context["stats"]["active_projects"], 1)
        self.assertEqual(response.context["stats"]["outstanding"], Decimal("1250.00"))
        self.assertEqual(response.context["stats"]["paid"], Decimal("0"))
        self.assertContains(response, "Onboarding automation")

    def test_dashboard_empty_state(self):
        Invoice.objects.all().delete()
        Project.objects.all().delete()
        Client.objects.all().delete()
        response = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects yet")


class ClientViewTests(PortalTestMixin, TestCase):
    def test_client_list_search_matches_company(self):
        response = self.client.get(reverse("portal:client_list"), {"q": "analytical"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Lovelace")

        response = self.client.get(reverse("portal:client_list"), {"q": "nobody"})
        self.assertNotContains(response, "Ada Lovelace")
        self.assertContains(response, "No clients found")

    def test_client_outstanding_is_not_multiplied_by_projects(self):
        Project.objects.create(
            client=self.client_record,
            name="Second project",
            budget=Decimal("900.00"),
            progress=10,
        )
        response = self.client.get(reverse("portal:client_list"))
        listed = list(response.context["clients"])[0]
        self.assertEqual(listed.outstanding, Decimal("1250.00"))

    def test_client_detail_shows_projects_and_invoices(self):
        response = self.client.get(self.client_record.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Onboarding automation")
        self.assertContains(response, "INV-TEST-001")

    def test_client_create(self):
        response = self.client.post(
            reverse("portal:client_create"),
            {
                "name": "Grace Hopper",
                "company": "Navy Systems",
                "email": "grace@example.com",
                "phone": "",
                "website": "",
                "notes": "",
            },
        )
        self.assertRedirects(
            response,
            reverse(
                "portal:client_detail",
                args=[Client.objects.get(email="grace@example.com").pk],
            ),
        )
        self.assertTrue(Client.objects.filter(email="grace@example.com").exists())

    def test_client_create_rejects_duplicate_email(self):
        response = self.client.post(
            reverse("portal:client_create"),
            {
                "name": "Duplicate",
                "company": "",
                "email": "ada@example.com",
                "phone": "",
                "website": "",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(Client.objects.count(), 1)

    def test_missing_client_returns_404(self):
        response = self.client.get(reverse("portal:client_detail", args=[9999]))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)


class ProjectViewTests(PortalTestMixin, TestCase):
    def test_project_list_filters_and_counts(self):
        Project.objects.create(
            client=self.client_record,
            name="Delivered thing",
            status=Project.Status.DELIVERED,
            progress=100,
        )
        response = self.client.get(reverse("portal:project_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["projects"]), 2)
        self.assertEqual(response.context["total"], 2)

        response = self.client.get(
            reverse("portal:project_list"), {"status": Project.Status.DELIVERED}
        )
        self.assertEqual(len(response.context["projects"]), 1)
        self.assertContains(response, "Delivered thing")
        self.assertNotContains(response, "Onboarding automation")

    def test_project_detail_renders_progress(self):
        response = self.client.get(self.project.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "40%")
        self.assertContains(response, "INV-TEST-001")

    def test_project_create_prefills_client(self):
        response = self.client.get(
            reverse("portal:project_create"), {"client": self.client_record.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].initial["client"], self.client_record
        )

    def test_project_progress_update(self):
        response = self.client.post(
            reverse("portal:project_progress", args=[self.project.pk]),
            {"progress": "75"},
        )
        self.assertRedirects(response, self.project.get_absolute_url())
        self.project.refresh_from_db()
        self.assertEqual(self.project.progress, 75)

    def test_project_progress_rejects_out_of_range(self):
        response = self.client.post(
            reverse("portal:project_progress", args=[self.project.pk]),
            {"progress": "140"},
            follow=True,
        )
        self.assertContains(response, "Progress must be between 0 and 100.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.progress, 40)

    def test_project_progress_requires_post(self):
        response = self.client.get(
            reverse("portal:project_progress", args=[self.project.pk])
        )
        self.assertEqual(response.status_code, 405)


class InvoiceViewTests(PortalTestMixin, TestCase):
    def test_invoice_list_runs_and_sums(self):
        response = self.client.get(reverse("portal:invoice_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["outstanding"], Decimal("1250.00"))
        self.assertContains(response, "INV-TEST-001")

    def test_invoice_list_overdue_filter(self):
        self.invoice.due_on = self.today - timedelta(days=3)
        self.invoice.save()

        response = self.client.get(
            reverse("portal:invoice_list"), {"status": "overdue"}
        )
        self.assertEqual(len(response.context["invoices"]), 1)

        self.invoice.status = Invoice.Status.PAID
        self.invoice.save()
        response = self.client.get(
            reverse("portal:invoice_list"), {"status": "overdue"}
        )
        self.assertEqual(len(response.context["invoices"]), 0)

    def test_invoice_create_generates_number_and_prefills_project(self):
        response = self.client.get(
            reverse("portal:invoice_create"), {"project": self.project.pk}
        )
        form = response.context["form"]
        self.assertEqual(form.initial["client"], self.client_record)
        self.assertEqual(form.initial["project"], self.project)
        self.assertEqual(form.initial["amount"], self.project.budget)
        self.assertTrue(form.initial["number"].startswith("INV-"))

    def test_invoice_create_post(self):
        response = self.client.post(
            reverse("portal:invoice_create"),
            {
                "client": self.client_record.pk,
                "project": self.project.pk,
                "number": "INV-TEST-002",
                "amount": "500.00",
                "status": Invoice.Status.DRAFT,
                "issued_on": self.today,
                "due_on": self.today + timedelta(days=14),
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("portal:invoice_list"))
        self.assertTrue(Invoice.objects.filter(number="INV-TEST-002").exists())

    def test_invoice_mark_paid_and_redirect(self):
        response = self.client.post(
            reverse("portal:invoice_mark_paid", args=[self.invoice.pk]),
            {"next": reverse("portal:invoice_list")},
        )
        self.assertRedirects(response, reverse("portal:invoice_list"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.paid_on, self.today)

    def test_invoice_mark_paid_ignores_external_next(self):
        response = self.client.post(
            reverse("portal:invoice_mark_paid", args=[self.invoice.pk]),
            {"next": "https://evil.example.com/"},
        )
        self.assertRedirects(response, reverse("portal:invoice_list"))


class AdminTests(PortalTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="test-pass-123"
        )
        self.client.force_login(self.admin_user)

    def test_admin_pages_load(self):
        for model_name in ("client", "project", "invoice"):
            response = self.client.get(f"/admin/portal/{model_name}/")
            self.assertEqual(response.status_code, 200, model_name)

    def test_admin_mark_paid_action(self):
        response = self.client.post(
            "/admin/portal/invoice/",
            {
                "action": "mark_paid",
                "_selected_action": [str(self.invoice.pk)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)


class SeedDemoTests(TestCase):
    def test_seed_demo_creates_records_and_is_idempotent(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        self.assertEqual(Client.objects.count(), 4)
        self.assertEqual(Project.objects.count(), 6)
        self.assertEqual(Invoice.objects.count(), 6)
        self.assertIn("Seeded", out.getvalue())

        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Client.objects.count(), 4)
        self.assertEqual(Project.objects.count(), 6)
        self.assertEqual(Invoice.objects.count(), 6)

    def test_seed_demo_reset_clears_records(self):
        Client.objects.create(name="Keep", email="keep@example.com")
        call_command("seed_demo", "--reset", stdout=StringIO())
        self.assertFalse(Client.objects.filter(email="keep@example.com").exists())
        self.assertEqual(Client.objects.count(), 4)
