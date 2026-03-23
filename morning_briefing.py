"""
Vietnam Deals — Morning Briefing
Sends a daily Telegram summary of pipeline status, contacts, and outreach replies.
Run at 08:00 via Windows Scheduled Task "VietnamMorningBriefing".
"""
import json
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
import os
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config — tokens are read from existing project files
# ---------------------------------------------------------------------------

GITHUB_TOKEN = "REDACTED_PAT"
GITHUB_OWNER = "sunfeilaoxiang"
GITHUB_REPO  = "vietnam-deals"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "vietnam-deals-briefing/1.0",
}

# Telegram credentials (from Documents/Claude/Projects/Telegram hook/config.json)
TELEGRAM_TOKEN   = "8693866142:AAFex6INm69lxkEYvPySCxsTaNB-Xre3juI"
TELEGRAM_CHAT_ID = 505364158

DASHBOARD_URL = "https://sunfeilaoxiang.github.io/vietnam-deals/outreach_dashboard.html"

# Local files
TRACKER_FILE       = r"C:\Users\dsdar\zalo-mcp\outreach_tracker.json"
BRIEFING_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefing_state.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gh_get(path):
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, headers=GITHUB_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def load_state():
    if os.path.exists(BRIEFING_STATE_FILE):
        with open(BRIEFING_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"reported_responses": []}


def save_state(state):
    with open(BRIEFING_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def hours_ago(iso_str):
    """Return how many hours ago an ISO 8601 timestamp was."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return round(delta.total_seconds() / 3600, 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Section A — Pipeline status
# ---------------------------------------------------------------------------

def section_pipeline():
    try:
        data = gh_get(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1")
        runs = data.get("workflow_runs", [])
        if not runs:
            return "📊 <b>Pipeline:</b> No runs found"
        run = runs[0]
        status     = run.get("status", "unknown")
        conclusion = run.get("conclusion") or "in_progress"
        created_at = run.get("created_at", "")
        h_ago      = hours_ago(created_at)
        age_str    = f"{h_ago}h ago" if h_ago is not None else "unknown time ago"

        if conclusion == "success":
            icon = "✅"
        elif status in ("in_progress", "queued"):
            icon = "⏳"
        elif conclusion in ("failure", "timed_out"):
            icon = "❌"
        else:
            icon = "⚠️"

        label = "In progress" if status == "in_progress" else conclusion.capitalize()
        return f"📊 <b>Pipeline:</b> {icon} {label} ({age_str})"
    except Exception as e:
        return f"📊 <b>Pipeline:</b> ⚠️ Unavailable ({e})"


# ---------------------------------------------------------------------------
# Section B — Contacts summary
# ---------------------------------------------------------------------------

def section_contacts():
    try:
        file_data = gh_get(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/data/contacts.json")
        raw = base64.b64decode(file_data["content"]).decode("utf-8")
        data = json.loads(raw)
        contacts = data.get("contacts", {})

        total     = len(contacts)
        with_phone = sum(1 for c in contacts.values() if c.get("broker_phone_full"))
        contacted  = sum(1 for c in contacts.values() if c.get("outreach_status") == "contacted")
        replied    = sum(1 for c in contacts.values() if c.get("outreach_status") == "replied")
        pending    = total - contacted - replied

        return (
            f"👥 <b>Contacts:</b> {total} total | {with_phone} with phones | "
            f"{pending} pending | {contacted} contacted | {replied} replied"
        )
    except Exception as e:
        return f"👥 <b>Contacts:</b> ⚠️ Unavailable ({e})"


# ---------------------------------------------------------------------------
# Section C — Zalo replies
# ---------------------------------------------------------------------------

def section_zalo(state):
    try:
        if not os.path.exists(TRACKER_FILE):
            return "📱 <b>Zalo replies:</b> No tracker found", []

        with open(TRACKER_FILE, encoding="utf-8") as f:
            tracker = json.load(f)

        sent = tracker.get("sent", {})
        reported = set(state.get("reported_responses", []))
        new_replies = []

        for lid, entry in sent.items():
            response = entry.get("response")
            if not response:
                continue
            key = f"{lid}:zalo"
            if key in reported:
                continue
            broker_name = entry.get("broker_name") or entry.get("phone") or lid
            snippet = str(response)[:80]
            new_replies.append((key, broker_name, lid, snippet))

        if not new_replies:
            return "📱 <b>Zalo replies:</b> No new replies", []

        lines = [f"📱 <b>Zalo replies ({len(new_replies)} new):</b>"]
        for key, name, lid, snippet in new_replies:
            lines.append(f"  • {name} ({lid}): &quot;{snippet}&quot;")

        new_keys = [r[0] for r in new_replies]
        return "\n".join(lines), new_keys

    except Exception as e:
        return f"📱 <b>Zalo replies:</b> ⚠️ Unavailable ({e})", []


# ---------------------------------------------------------------------------
# Section D — WhatsApp replies (read from tracker logged by /whatsapp-check)
# ---------------------------------------------------------------------------

def section_whatsapp(state):
    try:
        if not os.path.exists(TRACKER_FILE):
            return "💬 <b>WhatsApp:</b> No tracker found", []

        with open(TRACKER_FILE, encoding="utf-8") as f:
            tracker = json.load(f)

        replies = tracker.get("whatsapp_replies", [])
        reported = set(state.get("reported_wa_replies", []))
        new_replies = []

        for reply in replies:
            key = reply.get("key", "")
            if not key or key in reported:
                continue
            # Only report replies from last 48h
            reported_at = reply.get("reported_at", "")
            h = hours_ago(reported_at) if reported_at else None
            if h is not None and h > 48:
                continue
            broker_name = reply.get("broker_name") or reply.get("phone") or key
            listing_id = reply.get("listing_id", "")
            snippet = reply.get("message_snippet", "")[:80]
            new_replies.append((key, broker_name, listing_id, snippet))

        if not new_replies:
            total = len(replies)
            note = f" ({total} total logged)" if total else ""
            return f"💬 <b>WhatsApp replies:</b> No new replies{note}", []

        lines = [f"💬 <b>WhatsApp replies ({len(new_replies)} new):</b>"]
        for key, name, lid, snippet in new_replies:
            lid_str = f" ({lid})" if lid else ""
            lines.append(f"  • {name}{lid_str}: &quot;{snippet}&quot;")

        new_keys = [r[0] for r in new_replies]
        return "\n".join(lines), new_keys

    except Exception as e:
        return f"💬 <b>WhatsApp replies:</b> ⚠️ Unavailable ({e})", []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    state = load_state()

    print("Fetching pipeline status...")
    pipeline_line = section_pipeline()

    print("Fetching contacts...")
    contacts_line = section_contacts()

    print("Checking Zalo tracker...")
    zalo_line, new_zalo_keys = section_zalo(state)

    print("Checking WhatsApp replies from tracker...")
    whatsapp_line, new_wa_keys = section_whatsapp(state)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    message = (
        f"🌅 <b>Vietnam Deals Morning Briefing</b> — {now_str}\n\n"
        f"{pipeline_line}\n"
        f"{contacts_line}\n\n"
        f"{zalo_line}\n\n"
        f"{whatsapp_line}\n\n"
        f"🔗 <a href=\"{DASHBOARD_URL}\">Dashboard</a>"
    )

    print("\n" + "=" * 60)
    print("MESSAGE PREVIEW:")
    print("=" * 60)
    print(message)
    print("=" * 60 + "\n")

    print("Sending to Telegram...")
    try:
        result = tg_send(message)
        if result.get("ok"):
            print("✅ Telegram message sent.")
            # Mark new Zalo replies as reported
            if new_zalo_keys:
                state.setdefault("reported_responses", [])
                state["reported_responses"].extend(new_zalo_keys)
                print(f"Marked {len(new_zalo_keys)} Zalo reply/replies as reported.")
            # Mark new WhatsApp replies as reported
            if new_wa_keys:
                state.setdefault("reported_wa_replies", [])
                state["reported_wa_replies"].extend(new_wa_keys)
                print(f"Marked {len(new_wa_keys)} WhatsApp reply/replies as reported.")
            if new_zalo_keys or new_wa_keys:
                save_state(state)
        else:
            print(f"❌ Telegram error: {result}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")


if __name__ == "__main__":
    main()
