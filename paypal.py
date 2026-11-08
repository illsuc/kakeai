"""PayPal sandbox REST client (stdlib urllib only).

Uses OAuth2 client-credentials against api-m.sandbox.paypal.com and the
Invoicing v2 API. Never uses live credentials; the base URL is sandbox-only.
"""
import base64
import datetime
import json
import urllib.error
import urllib.request

BASE = "https://api-m.sandbox.paypal.com"


def _token(cfg):
    auth = base64.b64encode(
        ("%s:%s" % (cfg["paypal_client_id"], cfg["paypal_secret"])).encode()
    ).decode()
    req = urllib.request.Request(
        BASE + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": "Basic " + auth,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def _call(cfg, method, path, payload=None):
    tok = _token(cfg)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError("PayPal %s %s -> %s: %s" % (method, path, e.code, body[:500]))


def _normalize(inv):
    detail = inv.get("detail", {})
    amount = inv.get("amount", {})
    recipients = inv.get("primary_recipients", [])
    name = ""
    email = ""
    if recipients:
        billing = recipients[0].get("billing_info", {})
        name = (billing.get("name") or {}).get("full_name", "")
        email = billing.get("email_address", "")
    items = [
        {"name": i.get("name", ""),
         "quantity": (i.get("quantity") or {}).get("value", 1),
         "unit_amount": float((i.get("unit_amount") or {}).get("value", 0))}
        for i in inv.get("items", [])
    ]
    return {
        "id": inv.get("id", ""),
        "status": inv.get("detail", {}).get("status", inv.get("status", "")),
        "currency": detail.get("currency_code", ""),
        "amount": float(amount.get("value", 0)) if amount else sum(
            i["quantity"] * i["unit_amount"] for i in items),
        "recipient_name": name, "recipient_email": email, "items": items,
        "due_date": (detail.get("payment_term") or {}).get("due_date", ""),
        "created": detail.get("invoice_date", ""),
    }


def list_invoices(cfg):
    data = _call(cfg, "GET", "/v2/invoices?page_size=20&page=1")
    return [_normalize(i) for i in data.get("items", [])]


def _create_payload(intent):
    currency = intent.get("currency") or "JPY"
    items = intent.get("items") or [
        {"name": intent.get("note") or "Service", "quantity": 1, "unit_amount": 0}]
    due = intent.get("due_date") or (
        datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    payload = {
        "detail": {
            "currency_code": currency,
            "invoice_date": datetime.date.today().isoformat(),
            "note": intent.get("note") or "Created by Kakeai AI agent",
            "payment_term": {"term_type": "NET_30", "due_date": due},
        },
        "primary_recipients": [{
            "billing_info": {
                "email_address": intent.get("recipient_email") or "buyer@example.com",
                "name": {"full_name": intent.get("recipient_name") or "Customer"},
            }
        }],
        "items": [{
            "name": i["name"],
            "quantity": {"value": str(i.get("quantity", 1))},
            "unit_amount": {"currency_code": currency, "value": str(i.get("unit_amount", 0))},
            "unit_of_measure": {"unit_code": "QUANTITY"},
        } for i in items],
        "configuration": {"allow_partial_payment": False},
    }
    return payload


def _order_payload(intent):
    currency = intent.get("currency") or "JPY"
    items = intent.get("items") or [
        {"name": intent.get("note") or "Service", "quantity": 1, "unit_amount": 0}]
    amount = sum(i["quantity"] * i["unit_amount"] for i in items)
    return {
        "intent": "CAPTURE",
        "purchase_units": [{
            "description": (items[0]["name"] or "Service")[:127],
            "amount": {"currency_code": currency, "value": "%.2f" % amount},
        }],
        "application_context": {
            "brand_name": "Kakeai",
            "user_action": "PAY_NOW",
            "return_url": "http://localhost:8765/?order=returned",
            "cancel_url": "http://localhost:8765/?order=cancelled",
        },
    }


def _normalize_order(order):
    units = order.get("purchase_units", [])
    amount = {}
    desc = ""
    if units:
        amount = units[0].get("amount", {})
        desc = units[0].get("description", "")
    approve = ""
    for link in order.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            approve = link.get("href", "")
            break
    return {
        "id": order.get("id", ""),
        "status": order.get("status", ""),
        "currency": amount.get("currency_code", ""),
        "amount": float(amount.get("value", 0)) if amount.get("value") else 0,
        "description": desc,
        "approve_url": approve,
    }


def execute(intent, cfg):
    a = intent.get("action", "help")
    if a == "create_invoice":
        created = _call(cfg, "POST", "/v2/invoices", _create_payload(intent))
        inv = _normalize(created)
        if not inv.get("id"):
            inv["id"] = created.get("id", "")
        if intent.get("send_after") and inv.get("id"):
            _call(cfg, "POST", "/v2/invoices/%s/send" % inv["id"], {})
            inv["status"] = "SENT"
        return {"ok": True, "mock": False, "invoice": inv, "raw": created}
    if a == "create_order":
        created = _call(cfg, "POST", "/v2/checkout/orders", _order_payload(intent))
        order = _normalize_order(created)
        return {"ok": True, "mock": False, "order": order, "raw": created}
    if a == "send_invoice":
        iid = intent.get("invoice_id")
        if not iid:
            return {"ok": False, "mock": False, "error": "invoice_id required"}
        _call(cfg, "POST", "/v2/invoices/%s/send" % iid, {})
        return {"ok": True, "mock": False, "invoice": {"id": iid, "status": "SENT"}}
    if a == "list_invoices":
        return {"ok": True, "mock": False, "invoices": list_invoices(cfg)}
    if a == "summarize":
        invs = list_invoices(cfg)
        by = {}
        for inv in invs:
            key = "%s %s" % (inv["status"], inv["currency"])
            by[key] = by.get(key, 0) + inv["amount"]
        return {"ok": True, "mock": False, "count": len(invs), "totals_by_status_currency": by}
    return {"ok": True, "mock": False, "help": "create / send / list / summarize invoices and create checkout orders via natural language"}