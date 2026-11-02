from django.dispatch import Signal

payment_succeeded = Signal()
payment_failed = Signal()
payment_late_success = Signal()
payment_flagged = Signal()
payment_refunded = Signal()
inbounf_payment_received = Signal()