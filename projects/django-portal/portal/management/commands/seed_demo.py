"""Demo data for the client portal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from portal.models import Client, Invoice, Project


CLIENTS = [
    {
        "name": "Maya Chen",
        "company": "Northwind Studio",
        "email": "maya@northwind.studio",
        "phone": "+1 415 555 0134",
        "website": "https://northwind.studio",
        "notes": "Design studio. Prefers short weekly updates and Notion links.",
    },
    {
        "name": "Daniel Okafor",
        "company": "Okafor Legal",
        "email": "daniel@okaforlegal.com",
        "phone": "+44 20 7946 0912",
        "website": "https://okaforlegal.com",
        "notes": "Intake automation project. Sensitive data, keep everything local.",
    },
    {
        "name": "Priya Raman",
        "company": "Bloom & Co",
        "email": "priya@bloomand.co",
        "phone": "+91 80 4123 7788",
        "website": "https://bloomand.co",
        "notes": "E-commerce brand. Quarterly retainer, invoices net 14.",
    },
    {
        "name": "Tom Becker",
        "company": "Becker Fitness",
        "email": "tom@beckerfitness.de",
        "phone": "",
        "website": "https://beckerfitness.de",
        "notes": "Single-location gym. Wants booking and follow-up automations.",
    },
]

PROJECTS = [
    {
        "client": "maya@northwind.studio",
        "name": "Client onboarding automation",
        "status": Project.Status.IN_PROGRESS,
        "budget": Decimal("4200.00"),
        "progress": 65,
        "start_offset": -21,
        "due_offset": 12,
        "description": "Intake form → proposal → kickoff checklist, with Slack notifications and a shared dashboard.",
    },
    {
        "client": "maya@northwind.studio",
        "name": "Portfolio content pipeline",
        "status": Project.Status.REVIEW,
        "budget": Decimal("1800.00"),
        "progress": 90,
        "start_offset": -40,
        "due_offset": 3,
        "description": "Draft case studies from call notes, generate social variants, queue for approval.",
    },
    {
        "client": "daniel@okaforlegal.com",
        "name": "Intake triage assistant",
        "status": Project.Status.IN_PROGRESS,
        "budget": Decimal("6500.00"),
        "progress": 40,
        "start_offset": -14,
        "due_offset": 26,
        "description": "Classify inbound enquiries, extract matter details, and route to the right paralegal.",
    },
    {
        "client": "priya@bloomand.co",
        "name": "Retainer: support automation",
        "status": Project.Status.DELIVERED,
        "budget": Decimal("2400.00"),
        "progress": 100,
        "start_offset": -90,
        "due_offset": -30,
        "description": "Monthly retainer covering support macros, order-status replies, and reporting.",
    },
    {
        "client": "priya@bloomand.co",
        "name": "Abandoned cart sequence",
        "status": Project.Status.DISCOVERY,
        "budget": Decimal("1500.00"),
        "progress": 15,
        "start_offset": -5,
        "due_offset": 35,
        "description": "Map the current cart flow, define segments, then build a three-step recovery sequence.",
    },
    {
        "client": "tom@beckerfitness.de",
        "name": "Trial follow-up system",
        "status": Project.Status.ON_HOLD,
        "budget": Decimal("2100.00"),
        "progress": 30,
        "start_offset": -45,
        "due_offset": -6,
        "description": "Automated trial check-ins by SMS and email. Paused while the gym changes booking software.",
    },
]

INVOICES = [
    {
        "client": "maya@northwind.studio",
        "project": "Client onboarding automation",
        "number": "INV-2026-001",
        "amount": Decimal("2100.00"),
        "status": Invoice.Status.PAID,
        "issued_offset": -35,
        "due_offset": -21,
        "paid_offset": -24,
        "notes": "Deposit, 50% of project value.",
    },
    {
        "client": "maya@northwind.studio",
        "project": "Portfolio content pipeline",
        "number": "INV-2026-002",
        "amount": Decimal("1800.00"),
        "status": Invoice.Status.SENT,
        "issued_offset": -9,
        "due_offset": 5,
        "notes": "Net 14.",
    },
    {
        "client": "daniel@okaforlegal.com",
        "project": "Intake triage assistant",
        "number": "INV-2026-003",
        "amount": Decimal("3250.00"),
        "status": Invoice.Status.SENT,
        "issued_offset": -20,
        "due_offset": -3,
        "notes": "Milestone 1. Overdue, reminder sent.",
    },
    {
        "client": "priya@bloomand.co",
        "project": "Retainer: support automation",
        "number": "INV-2025-014",
        "amount": Decimal("2400.00"),
        "status": Invoice.Status.PAID,
        "issued_offset": -60,
        "due_offset": -46,
        "paid_offset": -50,
        "notes": "Quarterly retainer.",
    },
    {
        "client": "priya@bloomand.co",
        "project": "Abandoned cart sequence",
        "number": "INV-2026-004",
        "amount": Decimal("750.00"),
        "status": Invoice.Status.DRAFT,
        "issued_offset": 0,
        "due_offset": 21,
        "notes": "Kickoff invoice to send once scoping is signed off.",
    },
    {
        "client": "tom@beckerfitness.de",
        "project": "Trial follow-up system",
        "number": "INV-2026-005",
        "amount": Decimal("1050.00"),
        "status": Invoice.Status.SENT,
        "issued_offset": -28,
        "due_offset": -14,
        "notes": "Deposit. On hold pending platform migration.",
    },
]


class Command(BaseCommand):
    help = "Seed the portal with demo clients, projects, and invoices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing portal records before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Invoice.objects.all().delete()
            Project.objects.all().delete()
            Client.objects.all().delete()
            self.stdout.write("Cleared existing portal records.")

        today = timezone.localdate()
        clients = {}
        for row in CLIENTS:
            client, _ = Client.objects.update_or_create(
                email=row["email"],
                defaults={key: value for key, value in row.items() if key != "email"},
            )
            clients[row["email"]] = client

        projects = {}
        for row in PROJECTS:
            client = clients[row["client"]]
            fields = {
                key: value
                for key, value in row.items()
                if key not in {"client", "start_offset", "due_offset"}
            }
            project, _ = Project.objects.update_or_create(
                client=client,
                name=row["name"],
                defaults={
                    **fields,
                    "start_date": today + timedelta(days=row["start_offset"]),
                    "due_date": today + timedelta(days=row["due_offset"]),
                },
            )
            projects[(client.email, row["name"])] = project

        for row in INVOICES:
            client = clients[row["client"]]
            project = projects[(client.email, row["project"])]
            Invoice.objects.update_or_create(
                number=row["number"],
                defaults={
                    "client": client,
                    "project": project,
                    "amount": row["amount"],
                    "status": row["status"],
                    "issued_on": today + timedelta(days=row["issued_offset"]),
                    "due_on": today + timedelta(days=row["due_offset"]),
                    "paid_on": (
                        today + timedelta(days=row["paid_offset"])
                        if "paid_offset" in row
                        else None
                    ),
                    "notes": row["notes"],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(clients)} clients, {len(projects)} projects, "
                f"and {len(INVOICES)} invoices."
            )
        )
