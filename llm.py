"""AI layer: Gemini REST (free tier) with a deterministic rule-based fallback.

The fallback keeps the demo fully functional without any API key; when a
gemini_api_key is configured, intent parsing and reply rendering use the LLM.
"""
import calendar
import datetime
import json
import re
import urllib.request

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key=%s"
)

SYSTEM = """You are Kakeai, a PayPal assistant. Convert the user request (Japanese or English) into ONE JSON intent with exactly these keys:
{"action":"create_invoice"|"send_invoice"|"list_invoices"|"summarize"|"create_order"|"help",
 "recipient_name":string|null,"recipient_email":string|null,
 "items":[{"name":string,"quantity":integer,"unit_amount":number}]|null,
 "currency":"JPY"|"USD"|string|null,"due_date":"YYYY-MM-DD"|null,
 "invoice_id":string|null,"note":string|null,"send_after":boolean|null}
Rules: infer currency from ¥/円 (JPY) or $/USD (USD). "月末" means the last day of the current month. For send_invoice, invoice_id looks like INV-0001 or a PayPal invoice id. If the user asks to create AND send an invoice in one request, set action=create_invoice and send_after=true. A request for a checkout / payment link / 注文 / 決済 means action=create_order (a PayPal Orders v2 checkout, not an invoice). Output ONLY the JSON object."""


def _gemini(prompt, cfg):
    key = cfg.get("gemini_api_key")
    if not key:
        return None
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL % key, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _rules(msg):
    intent = {
        "action": "help", "recipient_name": None, "recipient_email": None,
        "items": None, "currency": None, "due_date": None,
        "invoice_id": None, "note": None, "send_after": None,
    }
    low = msg.lower()
    if re.search(r"一覧|リスト|list|show.*invoice", low):
        intent["action"] = "list_invoices"
    elif re.search(r"要約|まとめ|分析|summar|analys|report", low):
        intent["action"] = "summarize"
    elif re.search(r"チェックアウト|checkout|決済リンク|payment\s*link|支払いリンク|注文|create.*order|order.*for", low):
        intent["action"] = "create_order"
    elif re.search(r"送信|送って|send", low) and not re.search(r"作成|作って|請求書|invoice|create|bill", low):
        intent["action"] = "send_invoice"
    elif re.search(r"作成|作って|請求書|invoice|create|bill", low):
        intent["action"] = "create_invoice"
        if re.search(r"送信|送って|send", low):
            intent["send_after"] = True

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", msg)
    if email:
        intent["recipient_email"] = email.group(0)
    name = re.search(r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff]*?)\s*(?:さん|様|宛|へ)", msg)
    if name:
        intent["recipient_name"] = name.group(1)
    if not intent["recipient_name"]:
        en = re.search(r"\bfor\s+([A-Za-z][A-Za-z0-9 &.'-]+?)(?:\s*,|\s*$)", msg)
        if en:
            intent["recipient_name"] = en.group(1).strip()

    amt = re.search(r"[¥￥$]\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:円|yen|ドル|usd)", low)
    if amt:
        raw = amt.group(1) or amt.group(2)
        value = float(raw.replace(",", ""))
        intent["currency"] = "USD" if ("$" in msg or "usd" in low or "ドル" in msg) else "JPY"
        item_name = re.sub(r"[¥￥$][\d,.]+|[\d,.]+\s*(?:円|yen|ドル|usd)", "", msg)
        item_name = re.sub(r"due\s+end\s+of\s+month|end\s+of\s+month|月末|due\s+\d{4}-\d{2}-\d{2}", " ", item_name, flags=re.I)
        item_name = re.sub(r"(さん|様|宛|へ|請求書|作成|作って|送信|送って|を|に|の|して|ください|invoice|create|send|for|to)", " ", item_name, flags=re.I)
        if intent.get("recipient_name"):
            item_name = re.sub(re.escape(intent["recipient_name"]), " ", item_name, flags=re.I)
        item_name = re.sub(r"\b(a|an|the)\b", " ", item_name, flags=re.I)
        item_name = re.sub(r"[\s,、。]+", " ", item_name).strip(" ,、.。")
        intent["items"] = [{"name": item_name[:40] or "サービス料", "quantity": 1, "unit_amount": value}]

    iid = re.search(r"INV-\d{4}", msg, flags=re.I)
    if iid:
        intent["invoice_id"] = iid.group(0).upper()
    date = re.search(r"\d{4}-\d{2}-\d{2}", msg)
    if date:
        intent["due_date"] = date.group(0)
    elif "月末" in msg or "end of month" in low:
        t = datetime.date.today()
        intent["due_date"] = t.replace(day=calendar.monthrange(t.year, t.month)[1]).isoformat()
    return intent


def parse_intent(msg, cfg):
    out = _gemini(SYSTEM + "\n\nUser request: " + msg, cfg)
    if isinstance(out, dict) and out.get("action"):
        return out
    return _rules(msg)


def render_reply(msg, intent, result, cfg):
    prompt = (
        "You are Kakeai, a concise bilingual PayPal assistant. The user said: %s\n"
        "The parsed intent was: %s\nThe API result was: %s\n"
        "Write a short, friendly reply in the SAME language as the user (Japanese or English), "
        "summarizing what happened and the key numbers/ids. Return JSON: {\"reply\": \"...\"}"
        % (msg, json.dumps(intent, ensure_ascii=False), json.dumps(result, ensure_ascii=False))
    )
    out = _gemini(prompt, cfg)
    if isinstance(out, dict) and out.get("reply"):
        return out["reply"]
    # Deterministic fallback reply.
    a = intent.get("action")
    if not result.get("ok", True):
        return "エラー: %s" % result.get("error", "unknown")
    if a == "create_invoice":
        inv = result.get("invoice", {})
        return "請求書 %s を作成しました（%s %s / %s宛 / 状態: %s）。" % (
            inv.get("id"), inv.get("currency"), inv.get("amount"),
            inv.get("recipient_name"), inv.get("status"))
    if a == "send_invoice":
        inv = result.get("invoice", {})
        return "請求書 %s を送信しました（状態: %s）。" % (inv.get("id"), inv.get("status"))
    if a == "list_invoices":
        return "請求書は %d 件あります。" % len(result.get("invoices", []))
    if a == "summarize":
        return "集計: %s（全%d件）" % (
            json.dumps(result.get("totals_by_status_currency", {}), ensure_ascii=False),
            result.get("count", 0))
    if a == "create_order":
        o = result.get("order", {})
        return "チェックアウト %s を作成しました（%s %s / 状態: %s）。承認URL: %s" % (
            o.get("id"), o.get("currency"), o.get("amount"),
            o.get("status"), o.get("approve_url"))
    return "請求書の作成・送信・一覧・要約、チェックアウト作成を自然言語で指示できます。例:「田中さんへWeb制作150,000円の請求書を作成して送信」"