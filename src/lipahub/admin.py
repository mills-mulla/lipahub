from django.contrib import admin
from .models import Event,Outbox, Payment, Refund,Transition


class TransitionInline(admin.TabularInline):
    model = Transition
    extra = 0
    readonly_fields = ("from_status", "to_status", "source", "at")
    can_delete = False

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "amount", "currency", "status", "needs_review", "reference", "created_at")
    list_filter = ("status", "provider", "kind", "needs_review")
    search_fields = ("id", "reference", "provider_ref", "correlation_id")
    readonly_fields = [f.name for t in Payment._meta.fields]
    inlines = [TransitionInline]

    def has_add_permission(self, request):
        return False

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display  = ("id", "provider", "dedupe_key")
    list_filter = ("provider", "kind")

admin.site.register(Outbox)
admin.site.register(Refund)
