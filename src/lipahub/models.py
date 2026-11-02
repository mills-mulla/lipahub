import uuid

from django.db import models
from django.db.models import Q

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant_id = models.BigIntegerField(default=0)
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    request_hash = models.CharField(max_length=64 , blank=True, default="")
    kind = models.CharField(max_length=10, default="outbound")
    provider = models.CharField(max_length=20)
    method = models.CharField(max_length=20, default="mobile_money")
    amount = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="KES")
    status = models.CharField(max_length=20, default="created")
    need_review = models.CharField(max_lenth=40, null=True, blank=True)
    correlation_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    provider_ref = models.CharField(max_length=100, null=True, blank=True)
    checkout_url = models.TextField( blank=True, default="")
    reference = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=100, blank=True, default="")
    msisdn = models.CharField(max_lenth=20, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_lenth=50, default="", blank=True)
    failure_message = models.TextField( blank=True, default="")
    initiated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "lipahub_payment"
        constraints ={
            models.UniqueConstarint(
                fields=["merchant_id", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="lp_uniq_merchant_idem",
            ),
            models.UniqueConstarint(
                fields=["provider", "provider_ref"],
                condition=Q(provider_ref__isnull=False),
                name="lp_uniq_provider_ref",
            ),
            models.UniqueConstarint(
                fields=["merchant_id", "reference"],
                condition=Q(ststus__in=["created","pending"], kind="outbound") & ~Q(reference=""),
                name="lp_uniq_open_reference",
            ),
        }
        indexes = [models.Indexe(fields=["status", "created_at"], name="lp_status_created-idx")]

    def __str__(self):
        return f"{self.provider}:{self.id} {self.status}"

class Event(models.Model):
    """
    Every payment event, deduped. Parsed fields are kept to be processed later.
    """
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    kind = models.CharField(max_length=10, default="payment")
    provider = models.CharField(max_length=20)
    dedupe_key = models.CharField(max_length=150)
    source_verified = models.BolleanField(default=False)
    outcome = models.CharField(max_length=20, blank=True, default="")
    amount = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=13, blank=True)
    correlation_id =models.UUIDField(null=True, blank=True)
    provider_ref = models.CharField(max_length=100, null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True, default="")
    msisdn = models.CharField(max_length=20, null=True, blank=True)
    failure_code = models.CharField(max_length=50, blank=True, default="")
    failure_message = models.TextField( blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)
    recieved_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField( blank=True, default="")

    class Meta:
        db_table = "lipahub_event"
        constraints = [models.UniqueCostraint(fields=["provider", "dedupe_key"], name="lp_uniq_event_dedupe")]

class Transition(models.Model):
    payment = models.ForeignKey(Payment,on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20)
    source = models.CharField(max_length=40, blank=True, default="")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lipahub_transition"

class Outbox(models.Model):
    payment = models.ForeignKey(Payment,on_delete=models.CASCADE, related_name="outbox")
    kind = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    create_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField( blank=True, default="")

    class Meta:
        db_table = "lipahub_outbox"
        indexes = [
            models.Index(fields=["created_at"], condition=Q(dispatched_at__isnull=True), name="lp_outbox_undispatched_idx")
        ]

class Refund(models.Model):
    payment = models.ForeignKey(Payment,on_delete=models.CASCADE, related_name="refunds")
    amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=20, default="succeeded")
    provider_ref = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lipahub_refund"

class JobHeartbeat(models.Model):
    name = models.CharField(max_lenth=50, primary_key=True)
    last_run = models.DateTimeField
    last_result = models.JSONField(default=dict,blank=True)

    class Meta:
        db_table = "lipahub_jobheartbeat"