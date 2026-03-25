#!/usr/bin/env python3
"""
merge_contacts.py — Preserve outreach history across CI runs.

Downloads the current contacts.json from GitHub (HEAD of main) as the
source-of-truth backup, then merges outreach fields from that backup
into the freshly-written contacts.json produced by the extractors.

Why this is needed:
  CI does a fresh checkout each run. Extractors only write NEW listings
  with default outreach fields. Any listing whose ID changes (or that
  disappears from the scrape) loses its outreach history. This script
  restores it.

Run: python merge_contacts.py
Env vars:
  GITHUB_TOKEN  — auto-provided by GitHub Actions (preferred)
  GITHUB_PAT    — fallback personal access token
  DATA_DIR      — directory containing contacts.json (default: data)
"""

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OWNER = "sunfeilaoxiang"
REPO = "vietnam-deals"
BRANCH = "main"
REMOTE_PATH = "data/contacts.json"

# Fields we always want to restore from the backup (outreach history + manual corrections)
OUTREACH_FIELDS = [
    "outreach_status",
    "outreach_date",
    "outreach_channel",
    "response_date",
    "response_notes",
    "follow_up_dates",
    "broker_name",   # may have been manually corrected
    "broker_phone",  # may have been manually corrected
]

# Statuses that mean "we've done something with this contact" — keep even if listing vanished
ACTIVE_STATUSES = {"contacted", "responded", "meeting", "negotiating", "closed", "rejected"}


def download_github_contacts(token=None):
    """Download contacts.json from GitHub Contents API. Returns parsed dict or None."""
    url = (
        f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{REMOTE_PATH}"
        f"?ref={BRANCH}"
    )
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "vietnam-deals-merge-script",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            api_data = json.loads(resp.read())
            # GitHub returns file content as base64
            raw = base64.b64decode(api_data["content"]).decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("  contacts.json not found on GitHub — treating as fresh repo")
            return None
        print(f"  WARNING: GitHub API returned HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"  WARNING: Could not download from GitHub: {e}")
        return None


def _is_default_value(field, value):
    """Return True if the value is an unmodified default (not worth preserving)."""
    if value is None:
        return True
    if field == "outreach_status" and value == "pending":
        return True
    if field == "follow_up_dates" and value == []:
        return True
    return False


def merge_outreach_history(fresh_db, backup_db):
    """
    Merge outreach history from backup into fresh contacts database.

    Rules:
    - For contacts present in BOTH: copy non-default outreach fields from backup
      (fresh extraction data wins for everything else)
    - For contacts ONLY in backup with an active status: keep them in merged output
      (the listing may have been delisted but we still want the conversation history)
    - For contacts ONLY in fresh: keep as-is (new listings)
    """
    if backup_db is None:
        print("  No backup — skipping merge")
        return fresh_db

    backup_contacts = backup_db.get("contacts", {})
    fresh_contacts = fresh_db.get("contacts", {})

    merged = dict(fresh_contacts)  # start with everything the extractors found

    # Step 1: Restore outreach history for contacts that appear in both
    restored_count = 0
    for lid, backup_entry in backup_contacts.items():
        if lid not in merged:
            continue
        changed = False
        for field in OUTREACH_FIELDS:
            backup_val = backup_entry.get(field)
            if not _is_default_value(field, backup_val):
                merged[lid][field] = backup_val
                changed = True
        if changed:
            restored_count += 1

    # Step 2: Preserve active contacts whose listings disappeared from the scrape
    preserved_count = 0
    for lid, backup_entry in backup_contacts.items():
        if lid in merged:
            continue  # already handled above
        status = backup_entry.get("outreach_status", "pending")
        if status in ACTIVE_STATUSES:
            merged[lid] = dict(backup_entry)
            merged[lid]["_preserved_from_backup"] = True
            preserved_count += 1

    print(f"  Restored outreach history for {restored_count} contacts")
    if preserved_count:
        print(
            f"  Preserved {preserved_count} active contacts "
            "whose listings are no longer in the scrape"
        )

    fresh_db["contacts"] = merged
    fresh_db["last_merge"] = datetime.now().isoformat()
    return fresh_db


def main():
    data_dir = os.environ.get("DATA_DIR", "data")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT")

    contacts_file = Path(data_dir) / "contacts.json"
    backup_file = Path(data_dir) / "contacts_backup.json"

    print(f"\n{'='*60}")
    print("  merge_contacts.py — Preserving outreach history")
    print(f"{'='*60}\n")

    # --- Download GitHub HEAD version as source of truth ---
    print("  Downloading contacts.json from GitHub (source of truth)...")
    github_db = download_github_contacts(token)

    if github_db is not None:
        Path(data_dir).mkdir(exist_ok=True)
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(github_db, f, indent=2, ensure_ascii=False)
        github_count = len(github_db.get("contacts", {}))
        print(f"  Backup saved to {backup_file}: {github_count} contacts")
    else:
        print("  No GitHub backup available")
        # Fall back to any pre-existing local backup
        if backup_file.exists():
            with open(backup_file, encoding="utf-8") as f:
                github_db = json.load(f)
            fallback_count = len(github_db.get("contacts", {}))
            print(f"  Using existing local backup: {fallback_count} contacts")

    # --- Load fresh contacts.json (written by extractors this run) ---
    if not contacts_file.exists():
        print("  No fresh contacts.json found — nothing to merge, exiting")
        return

    with open(contacts_file, encoding="utf-8") as f:
        fresh_db = json.load(f)

    fresh_count = len(fresh_db.get("contacts", {}))
    print(f"  Fresh contacts.json: {fresh_count} contacts")

    # --- Merge ---
    merged_db = merge_outreach_history(fresh_db, github_db)
    merged_count = len(merged_db.get("contacts", {}))

    # --- Write merged result back ---
    with open(contacts_file, "w", encoding="utf-8") as f:
        json.dump(merged_db, f, indent=2, ensure_ascii=False)

    print(f"  Merged contacts.json written: {merged_count} contacts")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
