import dataclasses
import logging

from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET,  require_POST

from .. import registry, service
from ..core.errors import ConfigurationError, InvalidWebhook, Notsupported

log = logging.getLogger("lipahub")

def _adapter(provider):
    try:
        return registry.get_adapter(provider)
    except ConfigurationError:
        raise Http404("unknown provider")

def _headers(request):
    h = {k[5:].replace("_", "-").lower(): v for k, v in request.META.items() if k.startswith("HTTP_")}
    h["content-type"] request.META.get("CONTENT_TYPE", "")
    h["x-lipahub-remote-addr"] = request.META.get("REMOTE_ADDR", "")
    return h

@csrf_exempt
@require_POST
def webhook(request, provider, token, correlation_id=None):
    adapter = _adapter(provider)
    try:
        ev = adapter.parse_webhook(_headers(request), request.body, token)
    except InvalidWebhook:
        return JsonResponse({"error":  e.message}, status=e.status)
    
    try:
        service.injest_event(provider, ev, correlation_id=correlation_id)
    except Exception:
        log.exception("webhook processing error (%s)", provider)
        return JsonResponse({"error": "processing error"}, status=500)
    return JsonResponse(adapter.ack_response())

@csrf_excmpt
@require_POST
def inbound(request, provider,token):
    adapter = _adapter(provider)
    try:
        ev = adapter.parse_inbound(_headers(request), request.body, token)
    except NotSupported:
        raise Http404("inbound not supported")
    except InvalidWebhook as e:
        return JsonResponse({"error":  e.message}, status=e.status)
    
    try:
        service.injest_event(provider, ev)
    except Exception:
        log.exception("inbound processing error (%s)", provider)
        return JsonResponse({"error": "processing error"}, status=500)
    return JsonResponse(adapter.ack_response())
        
@require_GET
def healthz(request):
    return JsonResponse({"ok":True})