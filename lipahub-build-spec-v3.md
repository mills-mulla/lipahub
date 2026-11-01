# LipaHub: Build Spec v3 (self-contained brief for any AI)

Supersedes v1 and v2. Written from a pre-mortem of v2 and a code audit of the owner's real payment code (a Django finance app for an ISP/hotspot billing platform).

Legend: **[verify]** = a provider fact to confirm in the provider's own docs before relying on it. **[decide]** = an open choice to settle in a brainstorm before coding. **[adapt]** = a snippet that uses names from the owner's code and must be matched to the real models.

---

## 0. Read this first (instructions for the AI that receives this file)

You are a senior engineer pairing with the owner. This document contains the goals, the current-code audit, the target design and the build plan. Rules:

1. **Work one stage at a time.** Never dump the whole project. Start from the first unfinished stage in section 15 and stop after it.
2. **The owner writes the code.** For each stage give: a short brief (purpose, signatures, rules, edge cases), the tests to write first, and the verification commands. Review what the owner pastes back (bugs, security, style). Give complete files only when the owner asks, or for plumbing (Docker, CI, config).
3. **Brainstorm before architecture.** For anything marked **[decide]**, discuss options and tradeoffs first, and let the owner choose.
4. **Never invent provider facts.** Endpoints, headers, result codes, callback formats and IP lists must be confirmed in official docs. If unsure, say so and mark it **[verify]**.
5. **Money-safety first.** Every stage that touches payment state needs tests for duplicates, replays, races and failures before the feature is considered done.
6. **After each fix or step, give a verification command** and say what output to expect.
7. **Tests first, small commits.** Commit and push after every green stage.
8. Keep answers short enough to read on a phone. One stage per reply.
9. **The owner attaches the real source files listed in section 3.3.** Use the exact file, class and function names from the code map. Before writing a brief that depends on a file, check it was attached; if not, ask for it. Never guess a model field or function signature. Line numbers in this document come from the zip as reviewed and will drift after edits: search by function name.

---

## 1. Owner, context and goals

- Owner: Nomad, solo founder and final-year student in Kenya. Runs an ISP billing and network platform (TeraLinkX) with paying subscribers, and an algorithmic trading project.
- Core stack: Django/DRF, Vue 3, Celery, PostgreSQL (TimescaleDB), Redis, Docker Compose, nginx/Gunicorn/Daphne.
- Dev environment: Windows laptop (HP, AMD A10, limited resources) with WSL2 (Parrot) and Docker inside it, VS Code connected to WSL, a shared infra stack in `~/infra` (Postgres/Timescale, Redis, Adminer) used by all projects, one database and user per project via `newdb.sh`.
- Portfolio goal: a public GitHub portfolio of backend-heavy projects. This is **Project 2 of 10** (Project 1, a URL shortener, is built).
- Product goal: **LipaHub**, a pip-installable Django package that gives any Django project one reliable payments layer: mobile money (M-Pesa Daraja, Airtel Money, T-Kash if possible) and cards, behind one API, one state machine, safe webhooks and reconciliation.
- Dogfooding goal: TeraLinkX is the first real consumer. The package is extracted from hardened real code, not designed in a vacuum.

**Non-goals (v0.x):** disbursements/payouts, subscriptions, a merchant dashboard (Django admin is enough), storing card data of any kind, a wallet/credit system (that stays in the host app).

---

## 2. What good looks like (success criteria)

1. No payment can be lost, double-applied, or forged. A customer who paid is always eventually recognized (automatically or via a review queue).
2. Adding a provider means writing one adapter.
3. Everything important is covered by tests, including races and replays.
4. A stranger can `pip install` it, follow the README, and take a sandbox payment end to end.

---

## 3. Audit of the current implementation

Files reviewed (names from the owner's zip): `unified_payment.py`, `payment_gateway.py` (`MpesaGatewayHelper`, `TransactionQueueHelper`, `PaymentCallbackAPIView`, reconciliation), `queryDaraja.py`, `tasks.py`, `models.py` (`TransactionQueue`, `PaymentTransaction`). Line numbers are approximate. Nothing here was executed: findings come from reading the code, so **prove each one with a test before fixing it**.

### 3.1 What is already good (keep it)

- Atomic claim of a queue item (`mark_processing`), so the callback and the Celery fallback can't both deliver.
- A fallback Celery task that is revoked when the callback wins.
- A stuck-payment query task (`query_stuck_pending_transactions`) and a C2B pull reconciliation.
- Revenue recognized only after delivery; refund to balance if activation fails.
- C2B (customer-initiated paybill) handling with duplicate detection.
- A pending `PaymentTransaction` created at initiation, and WebSocket status push.

### 3.2 Findings

| ID | Severity | Summary |
|----|----------|---------|
| F1 | Critical | Callback endpoint has no authentication and the amount is never checked |
 ************************************************************
 BUT callback end point should be public to recieve responses
 ************************************************************
| F2 | Critical | Credit is refunded on failure/expiry but is not deducted at initiation (credit can be minted); refunds are not idempotent |
| F3 | High | STK push is retried on timeouts, causing duplicate prompts and orphaned payments |
| F4 | High | The queue row is created after the push, so a fast callback or a DB failure loses the link |
| F5 | Medium | A success callback after failure/expiry finds no queue item and is not flagged |
| F6 | Medium | Amounts are truncated with `int()`, and mixed payments can underpay |
| F7 | Medium | No duplicate-initiation guard (double tap = two prompts) |
| F8 | Medium | Hygiene: PII in logs, secrets cached, internals returned to clients, hardcoded brand prefix |

---

#### F1. Callback endpoint is unauthenticated, and the amount is never checked

**Where:** `payment_gateway.py`, `PaymentCallbackAPIView` (~L1419) and `create_payment_transaction_from_callback` (~L918).

```python
class PaymentCallbackAPIView(APIView):
    permission_classes = [AllowAny]
    ...
        callback_data = request.data
        logger.info(f"Received M-Pesa callback: {callback_data}")
```

**Why it matters:** Daraja STK callbacks carry no signature, so the endpoint must authenticate the *source*. "Nobody knows the URL" is not authentication. The URL appears in code (including a fallback default), follows a conventional path, is registered with Safaricom, and shows up in access logs and support tickets. The payer already knows their own `checkout_request_id` (it is in the API response and the WebSocket group name). Anyone who finds the URL can post a fake success for their own checkout id. The callback's `Amount` is also never compared with what was expected, so even a genuine callback for a different amount would be accepted. (Check whether nginx already restricts this path by source IP. If it does, this is mitigated, not fixed in code.)

**Fix, in four layers (defense in depth):**

1. Secret token in the path, compared in constant time:
```python
# urls.py
path("payments/callback/<str:token>/", PaymentCallbackAPIView.as_view()),
```
```python
# callback_security.py
import hmac
from decimal import Decimal
from django.conf import settings
from rest_framework.exceptions import PermissionDenied

def client_ip(request) -> str:
    # Trust this only if nginx SETS (not appends) the header:
    #   proxy_set_header X-Forwarded-For $remote_addr;
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")

def verify_callback_source(request, token: str) -> None:
    expected = settings.MPESA_CALLBACK_TOKEN          # long random value from the environment
    if not expected or not hmac.compare_digest(token, expected):
        raise PermissionDenied("bad callback token")
    allowed = getattr(settings, "MPESA_CALLBACK_IPS", None)  # Safaricom's published list [verify]
    if allowed and client_ip(request) not in allowed:
        raise PermissionDenied("source not allowed")
```
Register the callback URL with the token in it (in the gateway config and wherever the callback URL is built). Never log the token.

2. Compare the amount before delivering (inside the success handler, after claiming the queue item):
```python
def expected_mpesa_amount(queue_item) -> Decimal:
    return Decimal(str(queue_item.price)) - Decimal(str(queue_item.used_credit or 0))

if Decimal(str(callback_amount)) != expected_mpesa_amount(queue_item):
    queue_item.metadata["needs_review"] = "amount_mismatch"
    queue_item.save(update_fields=["metadata"])
    logger.error("amount mismatch for queue %s", queue_item.pk)
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})   # acknowledge, do not deliver
```

3. Re-query Safaricom before delivering (reuse the existing `query_stk_status` from `queryDaraja.py`): require `ResultCode == "0"`. If the query itself fails, leave the item pending and let the recovery job decide.
```python
result = query_stk_status(checkout_id)
if hasattr(result, "content"):          # the helper returns JsonResponse on errors (see F8)
    return ack()                        # unknown: leave pending, recovery job will retry
if str(result.get("ResultCode")) != "0":
    return ack()                        # not confirmed: never deliver
```

4. Redact logs (see F8) and apply the same token/IP check to the C2B validation and confirmation endpoints.

**Test first** (`tests/test_callback_security.py`, Django `APIClient`):
```python
def test_callback_rejects_wrong_token(api_client, pending_queue):
    r = api_client.post("/api/payments/callback/wrong/", success_payload(pending_queue), format="json")
    assert r.status_code == 403
    pending_queue.refresh_from_db()
    assert pending_queue.status == "pending"

def test_callback_rejects_amount_mismatch(api_client, settings, pending_queue):
    payload = success_payload(pending_queue, amount=1)
    r = api_client.post(f"/api/payments/callback/{settings.MPESA_CALLBACK_TOKEN}/", payload, format="json")
    pending_queue.refresh_from_db()
    assert pending_queue.status != "completed"      # use your real terminal status name [adapt]
```
**Verify:** `pytest -q tests/test_callback_security.py`, then on staging a callback with a wrong token must return 403.

---

#### F2. Credit can be minted: refunded on failure but never deducted at initiation

**Where:** `unified_payment.py` `handle_mixed_payment`, `tasks.py` `_refund_credit_if_needed` (~L871), `expire_pending_queues` (~L1272), `query_stuck_pending_transactions` (~L503), and `payment_gateway.py` `create_balance_transaction` (~L1061).

```python
# unified_payment.py, handle_mixed_payment: the balance is only CHECKED
if credit_amount > client.balance:
    return Response({... 'error': 'Insufficient balance for credit portion'}, ...)
...
queue_item = TransactionQueueHelper.create_payment_queue(..., used_credit=credit_amount, ...)
```
```python
# tasks.py, expire_pending_queues: a pending queue that expires CREDITS the balance
if txn.used_credit and txn.used_credit > 0:
    with db_transaction.atomic():
        client = ClientH.objects.select_for_update().get(pk=txn.user_id)
        client.balance += Decimal(str(txn.used_credit))
```
```python
# payment_gateway.py, create_balance_transaction: the DEBIT happens only at success callback
debit = queue_item.used_credit
...
raise ValueError(f"Transaction would result in negative balance: {balance_before - debit}")
```

**Why it matters (from reading the code; confirm on staging first):** if no debit happens at initiation, then every mixed payment that is abandoned, cancelled or expires gets `used_credit` *added* to the customer's balance, although nothing was ever taken. Repeating the attempt grows the balance. A second problem: the balance is only checked at initiation, so two mixed payments, or a payment plus another spend, can claim the same credit, and the debit at callback can then raise `ValueError` after the customer's M-Pesa money was already taken (callback returns 500, nothing delivered). A third: `_refund_credit_if_needed` is called from five places (`tasks.py` L458, L476, L579, L1402 and the inline copy in `expire_pending_queues`) and none is idempotent, so a payment can be refunded twice.

**Fix: reserve at initiation, release exactly once.**
```python
# finance/credit.py   [adapt model/field names]
from decimal import Decimal
from django.db import transaction
from finance.models import TransactionQueue
from users.models import ClientH

@transaction.atomic
def reserve_credit(client_id: int, amount: Decimal) -> None:
    """Debit the wallet now. Raises ValueError if the balance is not enough."""
    client = ClientH.objects.select_for_update().get(pk=client_id)
    if amount > client.balance:
        raise ValueError("Insufficient balance")
    client.balance -= amount
    client.save(update_fields=["balance"])

@transaction.atomic
def release_credit_once(queue_id) -> bool:
    """Give reserved credit back at most once. Never refunds credit that was not reserved."""
    queue = TransactionQueue.objects.select_for_update().get(pk=queue_id)
    if not queue.used_credit or queue.used_credit <= 0:
        return False
    if not queue.metadata.get("credit_reserved") or queue.metadata.get("credit_released"):
        return False
    client = ClientH.objects.select_for_update().get(pk=queue.user_id)
    client.balance += Decimal(str(queue.used_credit))
    client.save(update_fields=["balance"])
    queue.metadata["credit_released"] = True
    queue.save(update_fields=["metadata"])
    return True
```
Steps:
1. In `handle_mixed_payment`, after the queue row exists (see F4), call `reserve_credit(client.pk, credit_amount)` and set `queue_item.metadata["credit_reserved"] = True`. If the STK push is rejected outright, call `release_credit_once(queue_item.pk)`.
2. In `create_balance_transaction`, skip the debit when `metadata["credit_reserved"]` is true (only write the ledger entry).
3. Replace every `_refund_credit_if_needed(txn)` call and the inline refund in `expire_pending_queues` with `release_credit_once(txn.pk)`.

**Test first:**
```python
def test_abandoned_mixed_payment_does_not_mint_credit(client_with_balance_100, run_expire_job):
    start = client_with_balance_100.balance
    queue = initiate_mixed(client_with_balance_100, credit_amount=100)   # [adapt] helper
    assert client_with_balance_100.refresh_from_db() or client_with_balance_100.balance == start - 100
    expire(queue); run_expire_job()
    client_with_balance_100.refresh_from_db()
    assert client_with_balance_100.balance == start                      # back to 100, never 200

def test_release_is_idempotent(queue_with_reserved_credit):
    assert release_credit_once(queue_with_reserved_credit.pk) is True
    assert release_credit_once(queue_with_reserved_credit.pk) is False
```
**Verify on staging before and after the fix:** note the balance, start a mixed payment with credit, let it expire, compare the balance.

---

#### F3. STK push is retried on timeouts

**Where:** `payment_gateway.py`, `MpesaGatewayHelper.initiate_stk_push` (~L217 to L290).

```python
for attempt in range(3):
    try:
        response = requests.post(payment_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        ...
    except requests.RequestException as e:
        ...
        time.sleep(1)
```
**Why it matters:** after a read timeout the prompt may already be on the customer's phone, and the loop sends another. It also retries 4xx errors that can't succeed, blocks a worker with `sleep`, and when the final attempt times out there is no `checkout_request_id` (see F4). Also `payload["Items"]` is not a Daraja field: remove it.

**Fix:** one attempt for the push, no automatic retry. Retry only the *token* request.
```python
try:
    response = requests.post(payment_url, headers=headers, json=payload, timeout=(5, 20))
except requests.ConnectTimeout:
    return {"success": False, "error": "provider_unreachable", "outcome_known": True}   # never sent
except requests.RequestException:
    return {"success": False, "error": "provider_timeout", "outcome_known": False}      # may have been sent
if response.status_code >= 400:
    return {"success": False, "error": f"provider_http_{response.status_code}", "outcome_known": True}
```
When `outcome_known` is false, keep the queue row (F4) in a `pending_unknown` state and let reconciliation resolve it. Tell the customer to wait before retrying.

**Test:** mock `requests.post` to raise `ReadTimeout` and assert it was called exactly once.

---

#### F4. The queue row is created after the push

**Where:** `unified_payment.py` `handle_mpesa_payment` and `handle_mixed_payment`.

```python
result = MpesaGatewayHelper.initiate_stk_push(phone=phone_number, amount=int(final_price), ...)
if not result.get('success'):
    return Response({...}, status=status.HTTP_400_BAD_REQUEST)
queue_item = TransactionQueueHelper.create_payment_queue(..., checkout_id=result.get('checkout_request_id'), ...)
```
**Why it matters:** if the callback arrives before the row exists, or the insert fails (DB down, constraint), the customer paid and nothing records it until a recovery job finds it by phone and amount. After a push timeout there is no checkout id at all, and `query_stuck_pending_transactions` excludes rows without one (`checkout_request_id__isnull=False`).

**Fix: write first, then call, then update.**
1. Generate a `correlation_id = uuid4()`.
2. Create the queue row (and the pending `PaymentTransaction`) with `checkout_request_id=None`, `metadata["correlation_id"]`, status pending, and reserve credit (F2) in the same transaction.
3. Commit, then call the provider. Embed the correlation id in the callback URL (a path segment, e.g. `/payments/callback/<token>/<uuid>/`; confirm Daraja accepts it **[verify]**) and in `AccountReference`.
4. On success, store `checkout_request_id` on the row.
5. In the callback, look up by correlation id first, then by checkout id.
6. Recovery job: also pick up pending rows with no checkout id older than 3 minutes. Ask Daraja via the pull reconciliation, and if still unknown after the expiry window, mark `needs_review` and release the reserved credit only if no payment is found.

**Test:** simulate the callback arriving before step 4 completes (use the correlation id) and assert delivery happens once.

---

#### F5. A success after failure or expiry is not flagged

**Where:** `models.py` `TransactionQueue.get_pending_by_checkout_id` (~L1134).

```python
record = cls.objects.filter(checkout_request_id=checkout_id,
                            status__in=['pending', 'processing', 'Pending...']).first()
if record:
    return record
return cls.objects.filter(checkout_request_id=checkout_id, status='failed',
                          failure_category='system_error',
                          error_code='VOUCHER_PROCESSING_ERROR').first()
```
**Why it matters:** a genuine success that arrives after the item was marked failed (for example by `expire_pending_queues` at 30 minutes, or a misread result code) returns `None`, so money is recorded but nothing is delivered and nobody is told.

**Fix:** add `get_by_checkout_id` returning the row in any status. In the success path: if the row is `failed` or `expired` and the success is verified (F1 layers 2 and 3), credit the wallet with the received amount (your reconciliation code already has a helper for this), set `metadata["late_success"] = True`, and notify an admin. Never silently drop it.

**Test:** expire a queue, deliver a verified success callback, assert wallet credited once and the review flag set; deliver it again and assert nothing changes.

---

#### F6. Amounts are truncated

**Where:** `unified_payment.py`: `amount=int(final_price)` in the M-Pesa path and `amount=int(mpesa_amount)` in the mixed path (`mpesa_amount = final_price - credit_amount`).

**Why it matters:** with a fractional `credit_amount` the STK charge is rounded down and the difference is lost: package 100 with credit 0.01 charges 99 and takes 0.01 credit, total 99.01, up to about 1 KES short per purchase. Daraja's STK push takes whole shillings **[verify]**.

**Fix:** decide one rounding policy and apply it once, where the price is calculated; then reject anything fractional downstream.
```python
from decimal import Decimal

def whole_shillings(value) -> int:
    d = Decimal(str(value))
    if d != d.to_integral_value():
        raise ValueError("amount must be a whole number of shillings")
    return int(d)
```
Round the final price (after coupons) once in `calculate_final_price`; require `credit_amount` to be whole; call `whole_shillings(mpesa_amount)` before the push.

**Test:** fractional credit returns 400, and `whole_shillings(Decimal("99.50"))` raises.

---

#### F7. No duplicate-initiation guard

**Where:** `UnifiedPaymentAPIView.post` has no check before it calls the gateway.

**Why it matters:** a double tap or a retry after a slow response sends two prompts (and creates two queue rows) for the same package.

**Fix (two layers):**
1. A database rule that allows one open payment per client and package:
```python
# models.py, TransactionQueue.Meta   [adapt status names]
constraints = [
    models.UniqueConstraint(
        fields=["user", "package_code"],
        condition=models.Q(status__in=["pending", "processing", "Pending..."]),
        name="one_open_payment_per_user_package",
    )
]
```
2. An optional `Idempotency-Key` request header stored in `metadata`; a repeat returns the existing payment (same checkout id) instead of creating a new one.

On `IntegrityError`, return the existing open payment with a clear message. **Test:** two concurrent initiations produce one row.

---

#### F8. Hygiene

- **PII in logs:** `logger.info(f"Received M-Pesa callback: {callback_data}")` logs phone numbers. Redact `PhoneNumber`, `MSISDN` and names before logging.
- **Secrets cached:** the gateway config (consumer secret, passkey) is cached in Redis for an hour and stored in a DB JSON field. Keep secrets in environment variables or a secret store; cache only non-secret config.
- **Internals leaked:** several views return `str(e)` to the client. Return a generic message and a request id; log details server-side.
- **Hardcoded brand and currency:** the account reference prefix `TERALINKX_WAVES_` and `'KES'` live in code. Move to settings.
- **HTTP types in service code:** `queryDaraja.py` returns `JsonResponse` on errors, so every caller needs `hasattr(result, "content")`. Raise typed exceptions instead (`ProviderUnavailable`, `ProviderRejected`).
- **Token URL:** `queryDaraja.get_access_token` always calls the production OAuth URL even in test mode, while the query URL switches to sandbox. Use one environment switch.
- **Swallowed errors:** failure handlers catch `Exception` and still return 200. Keep returning 200 to the provider, but log with a payment id and increment a counter that monitoring can alert on.

**Test:** assert the callback log line contains no phone number (use `caplog`).

---

### 3.3 Code map: attach these files, edit exactly these places

Paths are relative to the Django app folder `finance/` unless stated. Search by function name; line numbers drift.

#### A. Attach: files that will be edited

| File | Why it is needed |
|------|------------------|
| `unified_payment.py` | Entry point: choosing credit, M-Pesa or mixed; initiation order; amounts |
| `payment_gateway.py` | `MpesaGatewayHelper`, `TransactionQueueHelper`, `PaymentCallbackAPIView`, C2B views, `MpesaPullReconciliation` (about 2,600 lines; if the AI can't read it all, send the classes listed in table C one at a time) |
| `queryDaraja.py` | STK status query, used for the re-check before delivery |
| `tasks.py` | Expiry, stuck-payment query, fallback task, and all the refund helpers |
| `models.py` | `TransactionQueue`, `PaymentTransaction`, `PaymentGateway` |
| `urls.py` | The callback and C2B routes |
| `migrations/0001_initial.py`, `0002_initial.py` | So the new migration `0003` chains correctly |
| `management/commands/test_callback.py` | Posts a test callback; must learn the new URL |

#### B. Attach: context files (read, not edited, unless noted)

| File | Why |
|------|-----|
| `credit_balance.py` | The pure-credit purchase path (`used_credit=price` near L651). Check that it debits at purchase and follows the same ledger rules |
| `authentications.py` | `MPESA_FAILURE_CODES`, reused later in `providers/daraja/codes.py` |
| `tests/api/test_endpoints.py`, `tests/unit/test_services.py`, `tests/integration/test_workflows.py` | So new tests follow your existing style and fixtures |
| `users/models.py` (outside the zip) | The `ClientH` model and its `balance` field, needed by `reserve_credit` |
| The model that stores balance ledger rows (find it: `grep -rn "class BalanceTransaction" .`) | Needed to fix `create_balance_transaction` |
| Project `settings.py` with all secrets removed | Where the new settings keys go |
| nginx site config for the API (secrets removed) | Whether `/api/payments/callback/` is already restricted by IP, and how `X-Forwarded-For` is set |

Not reviewed in this audit (do not attach unless asked): `querycheckout.py`, `handlers.py`, `cert_push.py`, `middleware.py`, `throttling.py`, bank-import models and views, and the unrelated finance modules.

#### C. Edit map (file, function, change, finding, Phase 0 step)

| File | Function or class | Change | Finding | Step |
|------|-------------------|--------|---------|------|
| `urls.py` | L85 `payments/callback/` | Route becomes `payments/callback/<str:token>/` (add `<uuid:cid>/` in step 0.4) | F1, F4 | 0.3, 0.4 |
| `urls.py` | L87 `payments/c2b/validate/`, and the C2B confirmation route | Same token treatment. `payments/c2b/register/` stays an authenticated admin endpoint | F1 | 0.3 |
| `payment_gateway.py` | `MpesaGatewayHelper.get_gateway_config` (L55) | Stop caching `consumer_secret` and `passkey` in Redis; remove the hardcoded fallback callback URL at L97 and read the base URL from settings | F8, F1 | 0.7, 0.3 |
| `payment_gateway.py` | `MpesaGatewayHelper.initiate_stk_push` (L192, loop at ~L217, `CallBackURL` at ~L230) | One attempt, no retry on read timeouts, remove the `Items` field, return `outcome_known`, build `CallBackURL` from base URL + token + correlation id, require whole shillings | F3, F4, F6 | 0.4, 0.6 |
| `payment_gateway.py` | `TransactionQueueHelper.create_payment_queue` (L296) | Accept `checkout_id=None` and a `correlation_id`; callable before the push; set `metadata["credit_reserved"]` | F2, F4 | 0.2, 0.4 |
| `payment_gateway.py` | `create_payment_transaction_from_callback` (L918) | Redact PII in logs; use the amount-check helper | F1, F8 | 0.3, 0.7 |
| `payment_gateway.py` | `create_balance_transaction` (L1061) | Skip the debit when `metadata["credit_reserved"]` is true; still write the ledger entry | F2 | 0.2 |
| `payment_gateway.py` | `PaymentCallbackAPIView` (L1419): `permission_classes`, `post`, `logger.info` | Call `verify_callback_source(request, token)`; log a redacted payload | F1, F8 | 0.3 |
| `payment_gateway.py` | `PaymentCallbackAPIView._handle_stk_callback` (L1460) | Look up by correlation id first, then checkout id | F4 | 0.4 |
| `payment_gateway.py` | `PaymentCallbackAPIView.handle_successful_payment` (L1620) | Amount check, `query_stk_status` re-query, late-success branch for `failed`/`expired` rows | F1, F5 | 0.3, 0.5 |
| `payment_gateway.py` | `PaymentCallbackAPIView.handle_failed_payment` (L1779) | Call `release_credit_once` (credit is now reserved at initiation) | F2 | 0.2 |
| `payment_gateway.py` | `MpesaPullReconciliation.register_pull` (L1975, `CallBackURL` at ~L1992) | Use the tokenized URL | F1 | 0.3 |
| `payment_gateway.py` | `C2BRegisterURLAPIView.post` (L2466, derivation at ~L2473) | Remove `config['callback_url'].replace('callback', 'c2b/validate')`; read explicit URLs from settings | F1 | 0.3 |
| `unified_payment.py` | `post` (L27) | Read `Idempotency-Key`; return the existing open payment on a duplicate | F7 | 0.4 |
| `unified_payment.py` | `calculate_final_price` (L107) | One rounding policy for the final price | F6 | 0.6 |
| `unified_payment.py` | `handle_mpesa_payment` (L217) | Reorder: create queue row, then push, then store the checkout id; `whole_shillings`; generic error text | F4, F6, F8 | 0.4, 0.6 |
| `unified_payment.py` | `handle_mixed_payment` (L293) | `reserve_credit` before the push; whole `credit_amount`; same reorder | F2, F4, F6, F7 | 0.2, 0.4, 0.6 |
| `unified_payment.py` | `handle_credit_payment` (L163) | Read only: confirm it debits at purchase | F2 | 0.2 |
| `queryDaraja.py` | `get_access_token`, `query_stk_status` | Raise typed exceptions instead of returning `JsonResponse`; one environment switch for token and query URLs | F8 (F1 depends on it) | 0.3, 0.7 |
| `tasks.py` | `cleanup_expired_transactions` (L407; refunds at ~L458 and ~L476) | Replace with `release_credit_once` | F2 | 0.2 |
| `tasks.py` | `query_stuck_pending_transactions` (L503; refund at ~L579) | Replace the refund; also select rows with no checkout id older than 3 min (use the correlation id or pull reconciliation) | F2, F4 | 0.2, 0.4 |
| `tasks.py` | `_process_confirmed_payment` (L689; `_refund_mpesa_to_balance` call at ~L862) | Make the M-Pesa refund idempotent with a `metadata` flag under row lock | F2 | 0.2 |
| `tasks.py` | `_refund_credit_if_needed` (L871) | Delegate to `release_credit_once` (or delete it) | F2 | 0.2 |
| `tasks.py` | `_refund_mpesa_to_balance` (L888) | Idempotent, row-locked, flagged | F2 | 0.2 |
| `tasks.py` | `expire_pending_queues` (L1272) | Replace the inline refund with `release_credit_once` | F2 | 0.2 |
| `tasks.py` | `check_payment_status_fallback` (L1304; nested `_push` at ~L1315, refund at ~L1402) | Replace the refund; honor late-success handling | F2, F5 | 0.2, 0.5 |
| `models.py` | `TransactionQueue` (L955) | Add `correlation_id` (UUID, unique, nullable) and the `UniqueConstraint` for one open payment per user and package | F4, F7 | 0.4 |
| `models.py` | `TransactionQueue.get_pending_by_checkout_id` (L1134) | Keep it; add `get_by_checkout_id` (any status) and `get_by_correlation_id` | F4, F5 | 0.4, 0.5 |
| `models.py` | `PaymentGateway` (L350) | Store only the base callback URL; append the token from settings at runtime so the secret is not in the database | F1, F8 | 0.3 |
| `migrations/0003_*.py` | New | Add the new field and constraint | F4, F7 | 0.4 |
| `management/commands/test_callback.py` | whole file | Include the token in the URL | F1 | 0.3 |
| `management/commands/seed_dev_data.py` (L88) | seed callback URL | It seeds `/api/finance/mpesa/callback/`, which is a different path from `payments/callback/`. Check which is live and align them | F1 | 0.3 |

**New files to create**

| File | Contents |
|------|----------|
| `callback_security.py` | `client_ip`, `verify_callback_source`, `expected_mpesa_amount` |
| `credit.py` | `reserve_credit`, `release_credit_once` |
| `money.py` | `whole_shillings` |
| `tests/api/test_callback_security.py` | wrong token 403, amount mismatch, replay, no PII in logs |
| `tests/unit/test_credit.py` | reserve once, release once, abandoned payment never mints credit |
| `tests/unit/test_money.py` | whole-shilling rules |
| `tests/integration/test_payment_races.py` | double initiation, callback before the checkout id is stored, late success |

**Settings and infrastructure to add**
- `settings.py`: `MPESA_CALLBACK_TOKEN` (long random value from the environment), `MPESA_CALLBACK_IPS` (Safaricom's published list **[verify]**), `MPESA_ACCOUNT_PREFIX`, `MPESA_CALLBACK_BASE_URL`, and the explicit C2B validation and confirmation URLs.
- nginx: set `X-Forwarded-For` to `$remote_addr` (set, don't append) so clients can't spoof the source IP.

**Rollout order for the callback change (so no payment is dropped)**
1. Deploy the new token route and keep the old route live, protected by the amount check and the status re-query only.
2. Switch STK requests to the new URL (it is sent with every request, so the change is immediate).
3. Wait for pending payments to drain (at least 30 minutes), then remove the old route.
4. C2B: the validation and confirmation URLs are registered with Safaricom. Check whether production allows re-registering them **[verify]** before changing those routes, and keep the old C2B route working until the new one is confirmed.

---

## 4. What the audit changes in the v2 design

| Gap in v2 | Added in v3 |
|-----------|-------------|
| Only payments created by us | **Inbound payments** (customer pays a paybill/till on their own). They start as `succeeded`, are attributed by account reference, and unmatched ones go to review |
| Late success after expiry ignored | Explicit **late-success policy** (section 7) |
| Callback matched only by provider ref | **Correlation id** in the callback URL, created before the provider call |
| Callback trusted | **Source token, optional IP allowlist, amount check, status re-query** |
| Signal after commit, nothing persisted | **Outbox** table so a crash can't lose fulfilment |
| Pull reconciliation absent | `list_transactions(since)` adapter capability |
| Wallet/credit unspecified | Out of scope for the package: the **host reserves credit** before calling it (F2) and uses the signals to capture or release |
| Routing by method and currency | **Explicit provider** when more than one can serve the request |
| Created-orphan and timeout cases | **Reaper** for `created` rows, and an explicit unknown-outcome path |

---

## 5. Target design

```
 host app (e.g. TeraLinkX)
   |  create_payment(...)                    signals: payment_succeeded / failed /
   v                                                  late_success / flagged / inbound
 +-----------------+      +------------------+              ^
 |  PaymentService |----->| Provider registry|              |
 |  state machine  |      +---------+--------+              |
 |  idempotency    |                | adapters:             |
 +--------+--------+      daraja | airtel | card | tkash | fake
          |                                                 |
 +--------v--------+   verify source -> store raw event -> process_event
 | Webhook receiver|-------------------------------------> apply transition
 | /webhooks/<p>/<token>/<payment_id>/                      write outbox row (same transaction)
 +-----------------+                                             |
 jobs: reaper (created), poll_pending, expire_stale,       outbox dispatcher (signals,
       reconcile (pull), purge_raw_payloads                 optional signed webhooks)
```

Principles:
1. **Write first, call second, update third.** The payment row exists and is committed before any provider call.
2. **Webhooks are hints; the provider's status query is the authority** for marking success.
3. **One transition function.** Everything that changes status goes through it, under `select_for_update`.
4. **Core is plain Python** (state machine, adapter protocol, money helpers). Django models and views sit on top. A FastAPI wrapper stays possible later.
5. **Money is an integer in minor units.** Provider formatting happens in the adapter.

---

## 6. Decisions

**Settled by the owner:** package name `lipahub`; pip-installable Django package; providers: Daraja (refactor of existing code), Airtel Money, a card provider, T-Kash if possible; built stage by stage, with the owner writing the code.

**Proposed by me (confirm or change):**

| ID | Decision | Proposal |
|----|----------|----------|
| D1 | Package vs service | Django package first; optional REST layer as an add-on |
| D2 | Provider routing | Explicit `provider` required when more than one provider matches |
| D3 | Card provider | The one you can get a sandbox for (Paystack, Flutterwave, Pesapal, IntaSend; Kenya is under Stripe's "Extended network", not direct signup) **[verify]** |
| D4 | T-Kash | No public developer docs found: ask Telkom, use an aggregator, or ship a documented stub |
| D5 | Phone numbers | Store E.164 in clear text, mask in logs, purge raw payloads on a schedule; encryption later |
| D6 | Outbound merchant webhooks | **Cut from v0.1** (needs SSRF protection). Signals + outbox only |
| D7 | Task runner | `sync` default (cron or management commands) and Celery optional; a `lipahub_doctor` command warns when jobs are not running |
| D8 | Database support | PostgreSQL (and MySQL 8) only, because of `select_for_update`; SQLite unsupported for the core |
| D9 | Versioning | 0.x until TeraLinkX has used it in production; no PyPI release before that |

---

## 7. State machine and policies

```
created --> pending --> succeeded --> refunded / partially_refunded
   |           |  \
   |           |   +--> failed
   |           +------> cancelled
   |           +------> expired
   +--> failed
inbound payments start at: succeeded
needs_review is a FLAG on a payment, not a status
```

- Allowed transitions live in one dict in one module. Everything else calls `transition(payment, new_status, source)`.
- `succeeded`, `failed`, `cancelled`, `expired` are terminal **except** for the late-success path.
- **Late success:** `failed | expired | cancelled → succeeded` is allowed only when the evidence is verified (authentic event plus matching amount plus status re-query, or a reconciliation hit). It sets `needs_review=true` and fires `payment_late_success`. Any other late event is logged and ignored.
- **Unknown outcome:** if `initiate()` times out, the payment stays `pending` with `provider_ref=None`. It is resolved by the correlation id in a callback, by reconciliation, or flagged `needs_review` at the expiry window. It is never retried automatically.
- **Created reaper:** a `created` payment older than `CREATED_REAPER_AFTER_SECONDS` is checked (it may have reached the provider before a crash). If nothing is found it becomes `failed(code="not_sent")`. It is never re-initiated automatically, because that could double-charge.
- **Amount rule:** a success whose amount differs from the payment's expected provider amount does not transition. It sets `needs_review="amount_mismatch"`.
- **No `status_query` capability:** `expire_stale` must not expire blindly. Flag `needs_review` instead.
- Every transition writes a `payment_transitions` row and, in the same transaction, an outbox row.

---

## 8. Data model

```sql
lipahub_payment
  id UUID PK, merchant_id BIGINT, idempotency_key VARCHAR(100), request_hash CHAR(64),
  kind VARCHAR(10)            -- outbound | inbound
  provider VARCHAR(20), method VARCHAR(20),
  amount BIGINT, currency CHAR(3),             -- minor units
  status VARCHAR(20), needs_review VARCHAR(40) NULL,
  correlation_id UUID UNIQUE,                  -- used in callback URL / account reference
  provider_ref VARCHAR(100) NULL,
  reference VARCHAR(100),                      -- the host's own reference (not unique)
  msisdn VARCHAR(20) NULL, metadata JSONB,
  failure_code VARCHAR(50), failure_message TEXT,
  created_at, updated_at, completed_at, expires_at TIMESTAMPTZ
  UNIQUE (merchant_id, idempotency_key)
  UNIQUE (provider, provider_ref) WHERE provider_ref IS NOT NULL
  PARTIAL UNIQUE (merchant_id, reference) WHERE status IN ('created','pending') AND kind='outbound'

lipahub_event        -- every raw provider event, deduped
  id BIGSERIAL, payment_id UUID NULL, provider, dedupe_key, UNIQUE(provider, dedupe_key),
  source_verified BOOLEAN, raw_payload JSONB (phone numbers scrubbed), received_at, processed_at, error

lipahub_transition   -- id, payment_id, from_status, to_status, source, at
lipahub_outbox       -- id, payment_id, kind, payload JSONB, created_at, dispatched_at NULL, attempts
lipahub_refund       -- id, payment_id, amount, status, provider_ref, created_at
lipahub_apikey       -- id, merchant_id, key_hash CHAR(64) UNIQUE, created_at (hash only)
```
Indexes: `(status, created_at)` for the jobs, `(provider, provider_ref)`, and `(dispatched_at) WHERE dispatched_at IS NULL` for the outbox.

---

## 9. Provider adapter protocol and the Daraja mapping

```python
@dataclass(frozen=True)
class Capabilities:
    status_query: bool = True
    refunds: bool = False
    inbound: bool = False
    list_transactions: bool = False

class ProviderAdapter(Protocol):
    name: str
    capabilities: Capabilities
    def supports(self, *, currency: str, method: str) -> bool: ...
    def initiate(self, payment: PaymentData) -> InitiateResult: ...          # no retries inside
    def query_status(self, payment: PaymentData) -> StatusResult: ...
    def parse_webhook(self, headers, body: bytes, token: str) -> ProviderEvent: ...   # verifies source
    def parse_inbound(self, headers, body: bytes, token: str) -> InboundEvent: ...
    def list_transactions(self, since: datetime) -> list[InboundEvent]: ...
    def refund(self, payment: PaymentData, amount: int) -> RefundResult: ...
```
Errors: `ProviderRejected` (definite no, so the payment fails), `ProviderUnavailable` (outcome unknown, so it stays pending), `InvalidWebhook` (400, never touches a payment). Adapters never import Django models: they receive and return plain dataclasses.

**Daraja adapter: map the existing code, don't rewrite it**

| Existing code | Becomes |
|---------------|---------|
| `MpesaGatewayHelper.get_gateway_config` + `get_access_token` | `DarajaAdapter._token()` (Django cache key per environment, TTL = expiry minus 5 min, one environment switch) |
| `MpesaGatewayHelper.initiate_stk_push` | `initiate()` (single attempt, whole shillings, correlation id in the callback URL) |
| `queryDaraja.query_stk_status` | `query_status()` (typed exceptions, not `JsonResponse`; `4999` = still processing) |
| `PaymentCallbackAPIView._handle_stk_callback` | `parse_webhook()` (+ the F1 source checks) |
| `PaymentCallbackAPIView._handle_c2b_callback` | `parse_inbound()` |
| `MpesaPullReconciliation` (in `payment_gateway.py`) | `list_transactions(since)` |
| `MPESA_FAILURE_CODES` (in `authentications.py`) | `providers/daraja/codes.py`, mapped to normalized failure codes |

Normalized failure codes: `cancelled_by_user`, `insufficient_funds`, `timeout`, `wrong_pin`, `invalid_number`, `provider_error`, `not_sent`.

Airtel Money **[verify]**: OAuth2 client credentials (cache the token), country and currency headers (`KE`, `KES`), collection via USSD push, a status enquiry, and a callback; confirm paths and callback authenticity in the Airtel developer portal. Production needs KYC, so start with the sandbox and apply early. Cards: hosted checkout only; the adapter returns a `checkout_url` and the result arrives by webhook; never touch card data.

---

## 10. Public API and settings

Python API:
```python
from lipahub.service import create_payment, get_payment
payment = create_payment(
    merchant=merchant, amount=15000, currency="KES", method="mobile_money",
    provider="daraja", msisdn="+254700000000", reference="ORDER-1",
    idempotency_key="order-1-attempt-1", metadata={},
)
```
Signals: `payment_succeeded`, `payment_failed`, `payment_late_success`, `payment_flagged`, `inbound_payment_received`. Receivers must be idempotent (delivery is at-least-once, from the outbox) and are called with `send_robust`.

Settings:
```python
LIPAHUB = {
    "PROVIDERS": {"daraja": {"adapter": "lipahub.providers.daraja.DarajaAdapter", "env": "sandbox"}},
    "TASK_RUNNER": "sync",                  # or "celery"
    "CALLBACK_BASE_URL": "https://example.com",
    "CALLBACK_TOKEN": env("LIPAHUB_CALLBACK_TOKEN"),
    "CALLBACK_ALLOWED_IPS": [],             # Safaricom's published list [verify]
    "PENDING_POLL_AFTER_SECONDS": 120,
    "CREATED_REAPER_AFTER_SECONDS": 90,
    "PAYMENT_EXPIRY_MINUTES": 30,
    "RAW_PAYLOAD_RETENTION_DAYS": 30,
}
```
Optional REST layer (v0.2): `POST /v1/payments` (Idempotency-Key header), `GET /v1/payments/{id}`, `GET /v1/payments`, `POST /v1/payments/{id}/refunds`, `POST /v1/webhooks/{provider}/{token}/{payment_id}/`, `GET /healthz`.

Django system checks (warnings): `ATOMIC_REQUESTS=True` on the default database; LocMem or Dummy cache outside DEBUG; non-PostgreSQL/MySQL 8 database; missing `CALLBACK_TOKEN`; `TASK_RUNNER="sync"` with no recent job heartbeat. `manage.py lipahub_doctor` reports: oldest `pending` age, payments flagged `needs_review`, events that failed processing, jobs last run time.

`create_payment` must not call the provider inside the host's transaction: it writes the row, then calls `transaction.on_commit(initiate)`, so a rolled-back host transaction never sends a push.

---

## 11. Jobs (all idempotent, all log the payment id and never a full phone number)

| Job | Cadence | Does |
|-----|---------|------|
| `process_event` | after each webhook | match by correlation id then provider ref, verify, transition, write outbox |
| `reaper_created` | 1 min | resolve `created` orphans (section 7) |
| `poll_pending` | 1-2 min | `query_status()` for `pending` older than the threshold; honor provider rate limits and the "still processing" code |
| `expire_stale` | 5 min | expire overdue `pending` after a final status query; flag if the query is unsupported |
| `reconcile_inbound` | 15 min | `list_transactions(since)` for providers that support it; create inbound payments or match |
| `dispatch_outbox` | 30 s | emit signals for undelivered outbox rows, mark dispatched |
| `purge_raw_payloads` | daily | scrub or delete raw payloads past retention |

In `sync` mode each job is a management command meant for cron or a systemd timer.

---

## 12. File structure

```
lipahub/
  pyproject.toml  README.md  LICENSE  CHANGELOG.md
  src/lipahub/
    __init__.py  apps.py  checks.py  signals.py  settings.py
    core/                      # plain Python, no Django imports
      money.py                 # whole_shillings, minor-unit helpers
      states.py                # statuses, allowed transitions
      errors.py                # ProviderRejected, ProviderUnavailable, InvalidWebhook
      types.py                 # PaymentData, InitiateResult, StatusResult, ProviderEvent, Capabilities
    models.py  admin.py
    service.py                 # create_payment, apply_event, transition(), reconcile
    registry.py                # provider registry and routing
    outbox.py
    jobs.py
    providers/
      base.py
      fake.py                  # scriptable: succeed, fail, timeout, duplicate and out-of-order events
      daraja/  adapter.py  codes.py
      airtel/  adapter.py
      card/    adapter.py
      tkash.py                 # stub or real
    api/                       # optional REST layer
    management/commands/       # run_jobs.py, lipahub_doctor.py
    migrations/
  tests/
    test_states.py  test_money.py  test_service.py  test_events.py
    test_jobs.py  test_outbox.py  test_checks.py
    providers/  test_daraja.py  test_airtel.py  fixtures/
    contract.py                # one suite every adapter (including fake and tkash) must pass
  example_project/             # tiny Django project used by tests and the README demo
  .github/workflows/ci.yml
```
Start as a normal Django app inside a working project (see Phase 1) and move it to this layout once it works.

---

## 13. Security checklist

- Webhook source verified before anything else (token in path, optional IP allowlist, constant-time compares), then an amount check, then a status re-query for success.
- No card data ever. No secrets in the database or cache; environment or a secret store only.
- Logs: payment id and masked phone only. Raw payloads scrubbed and purged.
- `select_for_update` on every transition; savepoints around idempotency inserts.
- Idempotency for creation, webhooks, refunds and credit release.
- Outbound webhooks (later) need SSRF protection: block private ranges, no redirects, short timeouts, per-merchant signing secret.
- Rate limit payment creation per merchant.
- Generic errors to clients, details in logs.

---

## 14. Test plan

- **Characterization tests first (Phase 0):** lock down what the current flows do (success, failure, duplicate callback, expiry) before changing anything.
- **State machine (pure):** every allowed and forbidden transition, terminal states, late-success rule.
- **Service:** idempotent create (same data returns the original, different data returns 409), concurrent duplicate creates, unknown-outcome path, created-reaper policy, amount mismatch flag.
- **Webhooks:** wrong token 403, replay is a no-op, callback before the provider reference is stored, out-of-order events, forged success with no matching payment.
- **Credit:** reserve and release exactly once; abandoned payment never mints credit.
- **Jobs:** each job twice in a row changes nothing the second time.
- **Adapters:** recorded provider responses (`responses` or `respx`) for success, rejection, timeout; status-code mapping tables; the shared contract suite.
- **Manual sandbox smoke script** per provider (not in CI) because recorded fixtures can't catch provider changes.
- **CI:** PostgreSQL service (TimescaleDB image if migrations need it), `ruff`, `pytest --cov`.

---

## 15. Build plan

Every step: tests first, then code, then the verify command, then commit and push. Realistic total: **3 to 5 weeks of evenings** for Phases 0 to 2. Do not start Phase 2 before Phase 1 is used in TeraLinkX.

### Phase 0: Harden the existing code (in TeraLinkX, before extracting anything)

The exact file, function and change for each step is in the edit map, section 3.3 (table C, last column).

| Step | Work | Verify |
|------|------|--------|
| 0.1 | Characterization tests for callback success, failure, duplicate, expiry | `pytest -q finance/tests -k payment` |
| 0.2 | Prove F2 on staging (note balance, abandon a mixed payment, wait for the expiry job), then fix with `reserve_credit` and `release_credit_once` | the balance returns to the starting value, never above it |
| 0.3 | F1: callback token, amount check, status re-query, log redaction (and the C2B endpoints) | wrong token returns 403, amount mismatch is not delivered |
| 0.4 | F4 + F3 + F7: row first, correlation id, single-attempt push, duplicate constraint | double tap creates one row, a mocked read timeout calls the provider once |
| 0.5 | F5: late-success path | expired queue plus a verified success credits the wallet once and flags it |
| 0.6 | F6: whole-shilling rule | fractional credit returns 400 |
| 0.7 | F8 hygiene items | caplog test shows no phone numbers |

### Phase 1: Extract `lipahub` core (v0.1)

| Step | Work | Verify |
|------|------|--------|
| 1.1 | Skeleton Django app (not packaged yet), `core/` with `states.py`, `money.py`, `errors.py`, tests first | `pytest tests/test_states.py tests/test_money.py` |
| 1.2 | Models and migrations, `transition()` under `select_for_update` | transition tests, concurrent test |
| 1.3 | `fake` provider, `create_payment` with idempotency and `on_commit` initiate | create the same payment twice and get one row |
| 1.4 | Webhook receiver, event dedupe, `process_event`, outbox | replay a webhook twice and see one transition and one outbox row |
| 1.5 | Jobs: reaper, poll, expire, outbox dispatcher, `lipahub_doctor` | stop the webhook and watch `poll_pending` resolve it |
| 1.6 | **Daraja adapter wrapping the existing TeraLinkX code**, contract suite | contract tests pass; sandbox STK push completes through `create_payment` |
| 1.7 | **Strangler step:** route one TeraLinkX payment flow through LipaHub behind a feature flag; keep the old code path | same flow works both ways in staging; flip the flag |
| 1.8 | Inbound payments (C2B) and `reconcile_inbound` | an unmatched paybill payment creates an inbound payment flagged for review |

### Phase 2: More providers (v0.2 and v0.3)

| Step | Work | Verify |
|------|------|--------|
| 2.1 | Airtel adapter (sandbox first; apply for production KYC early) | contract suite and a sandbox payment end to end |
| 2.2 | Card adapter (hosted checkout, webhook only) | a test card completes through the webhook only |
| 2.3 | T-Kash path: real, aggregator or documented stub | contract suite passes for it |
| 2.4 | Optional REST layer, admin views | curl flow from the README |

### Phase 3: Package and publish (v0.4+)

Move to the `src/` layout, build the wheel, add install tests, write the README (diagram, state machine, provider table, "how to add a provider", design decisions), tag `0.x`, and release to PyPI only after TeraLinkX has run it in production. Check that the name `lipahub` is free on PyPI first.

---

## 16. Definition of done (v0.1)

- [ ] Phase 0 fixes in place and tested; F1 to F8 each have a failing-then-passing test
- [ ] Forged, replayed, early and late callbacks are all handled safely (tested)
- [ ] No credit can be created or refunded twice (tested)
- [ ] One TeraLinkX flow runs through LipaHub in staging behind a flag
- [ ] Daraja passes the shared contract suite; the fake provider drives every failure mode
- [ ] `lipahub_doctor` reports clean on a healthy system
- [ ] CI green; coverage at least 80% on `core/`, `service.py` and `jobs.py`
- [ ] No secrets in the repo; `.env.example` present

---

## 17. First message to paste into a new AI chat

> I'm Nomad. I'm building LipaHub, a pip-installable Django payments package, extracted from the hardened payment code in my ISP billing app. Attached: the spec (v3) and the real source files listed in its section 3.3 (tables A and B). The spec has my goals, an audit of my current M-Pesa code (findings F1 to F8 with fixes), an exact edit map of which file and function to change, the target design and a stage-by-stage plan. Follow section 0 exactly: one stage at a time, I write the code, you give briefs, tests first, verification commands, and review. Use the real names from my files, never guess. We are at: **Phase 0, step 0.1** (characterization tests for the current callback flow). Check which files from section 3.3 I attached, tell me which are missing, then give me the brief for step 0.1. Keep each reply short enough to read on a phone.
