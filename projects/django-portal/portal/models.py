"""Models for the client portal: clients, projects, and invoices."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Client(models.Model):
    name = models.CharField(max_length=120)
    company = models.CharField(max_length=140, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.company or self.name

    def get_absolute_url(self) -> str:
        return reverse("portal:client_detail", args=[self.pk])


class Project(models.Model):
    class Status(models.TextChoices):
        DISCOVERY = "discovery", "Discovery"
        IN_PROGRESS = "in_progress", "In progress"
        REVIEW = "review", "In review"
        DELIVERED = "delivered", "Delivered"
        ON_HOLD = "on_hold", "On hold"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=160)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    progress = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("portal:project_detail", args=[self.pk])

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.status == self.Status.DELIVERED:
            return False
        return self.due_date < timezone.localdate()

    @property
    def status_tone(self) -> str:
        return {
            self.Status.DISCOVERY: "info",
            self.Status.IN_PROGRESS: "active",
            self.Status.REVIEW: "warning",
            self.Status.DELIVERED: "success",
            self.Status.ON_HOLD: "muted",
        }.get(self.status, "muted")


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invoices")
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    number = models.CharField(max_length=40, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField()
    paid_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self) -> str:
        return f"{self.number} · {self.client}"

    @property
    def is_overdue(self) -> bool:
        if self.status in {self.Status.PAID, self.Status.DRAFT}:
            return False
        return self.due_on < timezone.localdate()

    @property
    def display_status(self) -> str:
        return "overdue" if self.is_overdue else self.status

    @property
    def status_tone(self) -> str:
        return {
            self.Status.DRAFT: "muted",
            self.Status.SENT: "info",
            self.Status.PAID: "success",
            "overdue": "danger",
        }.get(self.display_status, "muted")

    def mark_paid(self) -> None:
        self.status = self.Status.PAID
        self.paid_on = timezone.localdate()
        self.save(update_fields=["status", "paid_on"])
