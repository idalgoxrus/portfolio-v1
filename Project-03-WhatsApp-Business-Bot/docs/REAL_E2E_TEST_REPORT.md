# Project #3 — Real E2E Report (WhatsApp Business Bot + Evolution API)

**Result: REAL E2E PASS**

## Test metadata

| Item | Value |
|---|---|
| Date | 2026-10-04 |
| Time of inbound message | **11:52:20 local** (08:52:20Z) |
| Time of outbound reply | **11:52:22 local** (08:52:22Z) |
| End-to-end latency | **2 s** inbound → reply sent |
| Instance | `project3pair11` |
| Evolution API | **v2.3.7** |
| Baileys | **7.0.0-rc.9** |
| FastAPI port | **8010** |
| Inbound transport | WhatsApp → Evolution → `messages.upsert` → HTTP webhook → FastAPI |
| Final instance state | `open` |

## 1. Inbound — real `messages.upsert`

| Field | Evidence |
|---|---|
| event | `messages.upsert` |
| instance | `project3pair11` |
| timestamp | 08:52:20Z (11:52:20 local) |
| `fromMe` | **`false`** |
| sender / chat | `371****6035@s.whatsapp.net` (masked) |
| LID form | `485****1488@lid`, `addressingMode: 'lid'` |
| pushName | `Inga` |
| text | **`Привет`** |
| messageType | `conversation` |
| message id | `AC0DBBE6…` |
| source | `android` |
| status | `DELIVERY_ACK` |

Not a synthetic probe: the earlier probe messages used a placeholder JID and the
texts `probe` / `auth probe`; those are excluded here.

## 2. Bot processing

| Field | Evidence |
|---|---|
| webhook delivery | `p.sendData-Webhook` → `http://host.docker.internal:8010/webhook`, `event: 'messages.upsert'` |
| accepted by FastAPI | yes — recorded with the correct `x-webhook-token` header; no 401 for this delivery |
| dropped? | no — the reply was actually produced and sent 2 s later |
| `bot.py` intent | **`greeting`** |
| reply prepared | **`Здравствуйте! 👋 Это демонстрационный WhatsApp Business Bot.`** |

The intent is established by the reply text: `bot.py` maps each intent to a distinct
constant, and the text returned matches `GREETING_REPLY` exactly, which only
`Intent.GREETING` produces (the matching keyword `привет` is in the greeting set).

Note on logs: `app/main.py` calls `_configure_logging()` only in its `__main__` block.
Started as `uvicorn app.main:app`, `logging.basicConfig` never runs, so `logger.info`
lines (`Webhook message handled: intent=…`) are not emitted, while `logger.warning`
lines still reach stderr. The successful outbound send is the proof the message was
handled.

## 3. Outbound — real Evolution `sendText`

| Field | Evidence |
|---|---|
| event | `send.message` (SEND_MESSAGE) |
| instance | `project3pair11` |
| endpoint | `message/sendText/project3pair11` |
| timestamp | 08:52:22Z (11:52:22 local) |
| recipient | `371****6035@s.whatsapp.net` (masked) |
| reply text | `Здравствуйте! 👋 Это демонстрационный WhatsApp Business Bot.` |
| message id | `3EB0A141D7…` |
| status in log | `PENDING` |
| sendText errors | **0** |

The reply was sent to the same JID the message arrived from, i.e. reply-to-sender.

## 4. Delivery confirmation

* **Recipient side:** the second WhatsApp displayed the reply — as reported by the user.
  This is the authoritative delivery confirmation.
* **Evolution logs:** no separate receipt/delivery-ack line is recorded for the
  outbound message; its logged status is `PENDING`. So delivery is NOT independently
  evidenced in the logs — only the successful send is.
* The *inbound* message did carry `status: 'DELIVERY_ACK'`.

## 5. Loop-prevention check (expected and correct)

A second inbound `messages.upsert` at 08:56:43Z from the same sender was ignored by
design: `main.py` does not reply when `is_from_me` is true. This confirms the
`fromMe` guard works and did not affect the 11:52 exchange.

## 6. Tests

```
pytest -q
113 passed, 1 warning
```

## 7. Unrelated log noise observed

Since the app on :8010 stopped, Evolution keeps failing webhook delivery with
`ECONNREFUSED` (745 lines), spread across all instances (`project3test` 487,
`project3live` 140, `project3pair9` 106, `project3pair11` 12). These are webhook
transport failures, **not** WhatsApp or sendText errors. Error codes seen in the log
are `ECONNREFUSED`, `ERR_BAD_REQUEST`, `ETIMEDOUT`; `sendText`-related errors: **0**.

## Conclusion

The full cycle is confirmed end to end on a real WhatsApp account:

```
second WhatsApp ("Привет", 11:52:20)
  -> Evolution messages.upsert
  -> webhook POST /webhook  (accepted, x-webhook-token)
  -> bot.py  intent=greeting
  -> Evolution message/sendText/project3pair11
  -> reply delivered to second WhatsApp (11:52:22)
```

**REAL E2E PASS**
