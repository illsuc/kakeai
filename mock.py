"""In-memory PayPal sandbox simulation for key-free demos. Clearly labeled MOCK."""
import copy
import datetime
import re

_TODAY = datetime.date.today()
_STORE = {
    "seq": 3,
    "order_seq": 0,
    "orders": [],
    "invoices": [
        {
            "id": "INV-0001", "status": "SENT", "currency": "JPY", "amount": 150000,
            "recipient_name": "田中商事", "recipient_email": "tanaka@example.com",
            "items": [{"name": "Web制作", "quantity": 1, "unit_amount": 150000}],
            "due_date": (_TODAY + datetime.timedelta(days=30)).isoformat(),
            "created": _TODAY.isoformat(),
        },
        {
            "id": "INV-0002", "status": "PAID", "currency": "USD", "amount": 800,
            "recipient_name": "Suzuki Design", "recipient_email": "suzuki@example.com",
            "items": [{"name": "Consulting", "quantity": 8, "unit_amount": 100}],
            "due_date": _TODAY.isoformat(), "created": _TODAY.isoformat(),
        },
    ],
}


def list_invoices():
    return copy.deepcopy(_STORE["invoices"])


def _total(inv):
    return sum(i["quantity"] * i["unit_amount"] for i in inv.get("items", []))


def execute(intent):
    a = intent.get("action", "help")
    if a == "create_invoice":
        _STORE["seq"] += 1
        inv = {
            "id": "INV-%04d" % _STORE["seq"],
            "status": "DRAFT",
            "currency": intent.get("currency") or "JPY",
            "recipient_name": intent.get("recipient_name") or "未指定",
            "recipient_email": intent.get("recipient_email") or "",
            "items": intent.get("items") or [{"name": intent.get("note") or "サービス料", "quantity": 1, "unit_amount": 0}],
            "due_date": intent.get("due_date") or (_TODAY + datetime.timedelta(days=30)).isoformat(),
            "created": _TODAY.isoformat(),
        }
        inv["amount"] = _total(inv)
        _STORE["invoices"].append(inv)
        if intent.get("send_after"):
            inv["status"] = "SENT"
        return {"ok": True, "mock": True, "invoice": inv}
    if a == "send_invoice":
        iid = intent.get("invoice_id")
        for inv in _STORE["invoices"]:
            if inv["id"] == iid:
                inv["status"] = "SENT"
                return {"ok": True, "mock": True, "invoice": inv}
        return {"ok": False, "mock": True, "error": "invoice not found: %s" % iid}
    if a == "list_invoices":
        return {"ok": True, "mock": True, "invoices": list_invoices()}
    if a == "summarize":
        invs = list_invoices()
        by = {}
        for inv in invs:
            key = "%s %s" % (inv["status"], inv["currency"])
            by[key] = by.get(key, 0) + inv["amount"]
        return {"ok": True, "mock": True, "count": len(invs), "totals_by_status_currency": by}
    if a == "create_order":
        _STORE["order_seq"] += 1
        items = intent.get("items") or [{"name": intent.get("note") or "サービス料", "quantity": 1, "unit_amount": 0}]
        amount = sum(i["quantity"] * i["unit_amount"] for i in items)
        oid = "MOCK-ORDER-%04d" % _STORE["order_seq"]
        order = {
            "id": oid, "status": "CREATED",
            "currency": intent.get("currency") or "JPY", "amount": amount,
            "description": items[0]["name"],
            "approve_url": "https://www.sandbox.paypal.com/checkoutnow?token=" + oid,
            "created": _TODAY.isoformat(),
        }
        _STORE["orders"].append(order)
        return {"ok": True, "mock": True, "order": order}
    return {"ok": True, "mock": True, "help": "請求書の作成/送信/一覧/要約、チェックアウト作成を自然言語で指示できます。"}