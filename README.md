# 掛け合い Kakeai — PayPal AI Agent

A dialogue AI agent that operates PayPal through natural language (Japanese & English).
PayPal AI Hackathon 2026 entry. **Meaningfully uses both PayPal and AI**:

- **PayPal**: OAuth2 client-credentials + **Invoicing v2** (create / send / list / summarize) and **Orders v2** (create a checkout, return the buyer approval link) against the PayPal **sandbox**.
- **AI**: Gemini (free tier) parses free-form JP/EN requests into structured payment intents and renders natural replies; a deterministic offline fallback keeps the app fully working without any key.

## Quickstart (no keys needed — mock mode)

```bash
python3 app.py
# open http://localhost:8765
```

Mock mode simulates the PayPal sandbox in memory and is clearly labeled `MOCK` in the UI and API responses.

## Live sandbox mode

1. Create a sandbox app at <https://developer.paypal.com/dashboard/applications/sandbox> → copy `client_id` / `secret`.
2. Create a free Gemini key at <https://aistudio.google.com/apikey>.
3. `cp config.example.json config.json` and fill in the three values, set `"mock": false`.
4. `python3 app.py` — the badge switches to `LIVE sandbox`.

`config.json` is gitignored; secrets never reach the browser (all API calls are server-side).

## Demo script (silent, under 3 minutes)

1. Show the chat + invoice list (mock or live sandbox).
2. Type: `田中さんへ Web制作 150,000円の請求書を作成して送信` → invoice created & sent, list updates.
3. Type: `請求書の一覧を見せて` → list.
4. Type: `売上を要約して` → AI summary by status/currency.
5. Type: `コンサルティング 50,000円のチェックアウトを作成` → Orders v2 checkout created, a PayPal approval link appears.
6. Type an English request → bilingual intent parsing.
7. Expand the `intent / result` panel to show the structured AI → PayPal API flow.

## Architecture

```
browser (static/index.html, no deps)
   │  POST /api/chat {message}
   ▼
app.py (stdlib ThreadingHTTPServer)
   ├─ llm.py    Gemini REST → JSON intent (offline rule fallback)
   ├─ paypal.py OAuth2 + Invoicing v2 + Orders v2 (sandbox only)
   └─ mock.py   in-memory sandbox simulation (key-free demo)
```

## Requirements / contest mapping

| Requirement | How |
|---|---|
| Meaningful PayPal use | Invoicing v2 create/send/list/summarize + Orders v2 checkout via sandbox OAuth |
| Meaningful AI use | LLM intent parsing + bilingual reply rendering |
| Public open-source repo | This repository (MIT) |
| Demo video < 3 min, shows it working | Silent screen recording of the flows above |
| Sandbox test credentials | Provided in the Devpost submission form |

## Security notes

- Sandbox base URL is hardcoded (`api-m.sandbox.paypal.com`); live credentials are never used.
- Secrets live only in server-side `config.json` (gitignored).
- No external frontend dependencies; no data leaves the machine except PayPal/Gemini API calls you configure.

## License

MIT — see LICENSE.