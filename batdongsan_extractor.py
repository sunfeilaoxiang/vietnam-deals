#!/usr/bin/env python3
"""
Batdongsan Authenticated Phone Extractor
Backfills full phone numbers for contacts.json entries that were extracted without login.
Loads cookies from BATDONGSAN_COOKIES env var (raw JSON) or cookies/batdongsan.json file.
"""

import json
import os
import re
import time
from pathlib import Path
from datetime import datetime


def load_cookies(cookies_dir="cookies"):
    """Load batdongsan cookies from env var or file."""
    raw = os.environ.get("BATDONGSAN_COOKIES", "")
    if raw:
        try:
            cookies = json.loads(raw)
            print(f"  Loaded {len(cookies)} cookies from BATDONGSAN_COOKIES env var")
            return cookies
        except Exception as e:
            print(f"  WARNING: Failed to parse BATDONGSAN_COOKIES env var: {e}")

    cookie_file = Path(cookies_dir) / "batdongsan.json"
    if cookie_file.exists():
        with open(cookie_file, encoding="utf-8") as f:
            cookies = json.load(f)
        print(f"  Loaded {len(cookies)} cookies from {cookie_file}")
        return cookies

    print("  ERROR: No batdongsan cookies available.")
    return []


def normalize_phone(phone_str):
    phone = re.sub(r'[\s\-\.\(\)]', '', phone_str)
    if phone.startswith('0'):
        phone = '+84' + phone[1:]
    elif phone.startswith('84') and not phone.startswith('+84'):
        phone = '+' + phone
    elif not phone.startswith('+'):
        phone = '+84' + phone
    return phone


def scrape_phone_from_page(page):
    content = page.content()
    tel_match = re.search(r'href="tel:(\+?84\d{8,10}|0\d{9,10})"', content)
    if tel_match:
        return normalize_phone(tel_match.group(1))
    for m in re.finditer(r'(0\d{2,3}[\s.]?\d{3}[\s.]?\d{3,4})', content):
        candidate = m.group(1)
        if '*' not in candidate:
            cleaned = re.sub(r'[\s.]', '', candidate)
            if len(cleaned) >= 10:
                return normalize_phone(cleaned)
    return None


def click_reveal_phone(page):
    selectors = [
        'button:has-text("Hi\u1ec7n s\u1ed1")',
        'a:has-text("Hi\u1ec7n s\u1ed1")',
        'span:has-text("Hi\u1ec7n s\u1ed1")',
        'div:has-text("Hi\u1ec7n s\u1ed1")',
        'text="Hi\u1ec7n s\u1ed1"',
        'button:has-text("Xem s\u1ed1")',
        'a:has-text("Xem s\u1ed1 \u0111i\u1ec7n tho\u1ea1i")',
        'button:has-text("Xem s\u1ed1 \u0111i\u1ec7n tho\u1ea1i")',
        '[data-action*="phone"]',
        '[class*="ShowPhone"]',
        '[class*="show-phone"]',
        '[class*="phone-show"]',
        '[class*="re__contact-phone"]',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"    Clicked: {sel}")
                return True
        except Exception:
            continue
    return False


def run_batdongsan_extraction(data_dir="data", cookies_dir="cookies"):
    from playwright.sync_api import sync_playwright

    print(f"\n{'='*60}")
    print(f"  Batdongsan Phone Extractor - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    contacts_file = Path(data_dir) / "contacts.json"
    if not contacts_file.exists():
        print("ERROR: contacts.json not found")
        return

    with open(contacts_file, encoding="utf-8-sig") as f:
        contacts_db = json.load(f)

    targets = []
    for lid, entry in contacts_db["contacts"].items():
        if entry.get("portal") != "batdongsan":
            continue
        if entry.get("broker_phone_full"):
            continue
        url = entry.get("listing_url", "")
        if not url or "batdongsan.com.vn" not in url:
            continue
        targets.append((lid, entry))

    print(f"Batdongsan entries needing phone extraction: {len(targets)}")
    if not targets:
        print("Nothing to do.")
        return

    cookies = load_cookies(cookies_dir)
    if not cookies:
        print("Cannot proceed without cookies - aborting.")
        return

    updated = 0
    failed = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="vi-VN",
        )

        try:
            context.add_cookies(cookies)
            print(f"  Added {len(cookies)} cookies to browser context\n")
        except Exception as e:
            print(f"  WARNING: context.add_cookies failed: {e}")
            good = 0
            for ck in cookies:
                try:
                    context.add_cookies([ck])
                    good += 1
                except Exception:
                    pass
            print(f"  Added {good}/{len(cookies)} cookies individually\n")

        page = context.new_page()
        last_api_phone = {}

        def on_response(response):
            url = response.url
            if "batdongsan.com.vn" not in url:
                return
            if not any(kw in url for kw in ("phone", "contact", "broker", "agent", "show")):
                return
            try:
                body = response.text()
                m = re.search(r'(?:phone|sdt|so_dt)[\"\':\s]+([0\d]\d{8,9})', body, re.IGNORECASE)
                if m and '*' not in m.group(1):
                    last_api_phone['value'] = normalize_phone(m.group(1))
            except Exception:
                pass

        page.on("response", on_response)

        for i, (lid, entry) in enumerate(targets):
            url = entry["listing_url"]
            print(f"[{i+1}/{len(targets)}] {url[:80]}")
            last_api_phone.clear()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2500)

                current_url = page.url
                if "login" in current_url or "dang-nhap" in current_url:
                    print("  ERROR: Session expired / not logged in. Aborting.")
                    break

                clicked = click_reveal_phone(page)
                if clicked:
                    page.wait_for_timeout(2000)

                phone = last_api_phone.get('value')
                if not phone:
                    phone = scrape_phone_from_page(page)
                if not phone:
                    try:
                        body_text = page.inner_text("body")
                        for m in re.finditer(r'(0\d{2,3}[\s.]?\d{3}[\s.]?\d{3,4})', body_text):
                            candidate = m.group(1)
                            if '*' not in candidate:
                                cleaned = re.sub(r'[\s.]', '', candidate)
                                if len(cleaned) >= 10:
                                    phone = normalize_phone(cleaned)
                                    break
                    except Exception:
                        pass

                if phone:
                    print(f"  + {phone}")
                    e = contacts_db["contacts"][lid]
                    e["broker_phone"] = phone
                    e["broker_phone_full"] = True
                    e["no_cookies"] = False
                    e["contact_method"] = "whatsapp"
                    e["phone_extracted_at"] = datetime.now().isoformat()

                    broker_name = e.get("broker_name")
                    if phone not in contacts_db["brokers"]:
                        contacts_db["brokers"][phone] = {
                            "name": broker_name,
                            "phone": phone,
                            "first_seen": datetime.now().isoformat(),
                            "listings": [lid],
                            "portal": "batdongsan",
                        }
                    else:
                        if lid not in contacts_db["brokers"][phone]["listings"]:
                            contacts_db["brokers"][phone]["listings"].append(lid)
                    updated += 1
                else:
                    print(f"  x No phone found (clicked={clicked})")
                    failed += 1

                time.sleep(1)

            except Exception as ex:
                print(f"  x Error: {ex}")
                failed += 1

        page.close()
        context.close()
        browser.close()

    full = sum(1 for e in contacts_db["contacts"].values() if e.get("broker_phone_full"))
    masked = sum(
        1 for e in contacts_db["contacts"].values()
        if e.get("broker_phone") and not e.get("broker_phone_full")
    )
    contacts_db["stats"]["phone_full"] = full
    contacts_db["stats"]["phone_masked"] = masked
    contacts_db["last_updated"] = datetime.now().isoformat()

    with open(contacts_file, "w", encoding="utf-8") as f:
        json.dump(contacts_db, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  Done: {updated} phones extracted, {failed} failed")
    print(f"  Total full phones in DB: {full}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", "data")
    cookies_dir = os.environ.get("COOKIES_DIR", "cookies")
    run_batdongsan_extraction(data_dir=data_dir, cookies_dir=cookies_dir)
