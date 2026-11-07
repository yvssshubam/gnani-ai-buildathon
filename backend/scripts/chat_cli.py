"""Talk to the running backend from your terminal, as a caller.

Usage (server must be running):
    python scripts/chat_cli.py
    python scripts/chat_cli.py --lang ta-IN      # tell the server the language, like Prisma would

Commands while chatting:
    /drop     simulate the network cutting the call
    /ticket   print the current ticket
    /quit     exit
"""
import argparse
import json

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--lang", default=None)
args = parser.parse_args()

c = httpx.Client(base_url=args.url, timeout=30)
start = c.post("/api/calls", json={}).json()
call_id = start["call_id"]
print(f"\n[call {call_id} from {start['caller_number']}]")
print(f"AGENT: {start['greeting']}\n")


def show_ticket(t):
    loc = t["location"]
    print("\n---- ticket", t["id"], "----")
    print(f"priority: {t['priority']}  reasons: {t['priority_reasons']}  alert human: {t['escalate_to_human']}")
    print(f"language: {t['language']}  interpreter: {t['needs_interpreter']}")
    print(f"location: {json.dumps({k: v for k, v in loc.items() if v not in (None, False)}, ensure_ascii=False)}")
    print(f"people: {t['people_count']}  vulnerable: {t['vulnerable']}  medical: {t['medical_need']}")
    print(f"danger: {json.dumps({k: v for k, v in t['danger'].items() if v is not None})}")
    print(f"needs: {t['needs']}  status: {t['status']}  call: {t['call_state']}  follow-up: {t['followup_reasons']}")
    print("-" * 30 + "\n")


while True:
    try:
        text = input("YOU:   ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text == "/quit":
        break
    if text == "/ticket":
        show_ticket(c.get(f"/api/tickets/{call_id}").json())
        continue
    if text == "/drop":
        show_ticket(c.post(f"/api/calls/{call_id}/drop").json()["ticket"])
        break
    r = c.post(f"/api/calls/{call_id}/turn", json={"text": text, "lang": args.lang}).json()
    how = "LLM" if r.get("used_llm") else "quick"
    print(f"AGENT: {r['reply']}   [{r['action']}, {r.get('turn_ms', '?')} ms, {how}]")
    if r.get("used_llm"):
        print(f"       (ack: {r.get('ack_status')})")
    if r["done"]:
        show_ticket(r["ticket"])
        print(f"LLM calls this call: {r.get('llm_calls_total')}, tokens: {r.get('tokens_total')}")
        break