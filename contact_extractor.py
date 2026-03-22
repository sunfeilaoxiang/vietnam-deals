#!/usr/bin/env python3
"""
Vietnam Property Contact Extractor — Playwright Edition
Takes listings from published_listings.json, visits each listing page
with authenticated cookies, and extracts full contact information
(phone numbers, broker names, WhatsApp links, form URLs).

Runs as Step 2 in the GitHub Actions pipeline, after scraper.py.
"""

import json
import re
import os
import time
import sys
from datetime import datetime
from pathlib import Path


def load_cookies(cookies_dir="cookies"):
    """Load saved browser cookies for each portal."""
    cookies = {}
    cookies_path = Path(cookies_dir)
    for portal_file in cookies_path.glob("*.json"):
        portal_name = portal_file.stem  # e.g., "batdongsan", "dotproperty"
        with open(portal_file, encoding="utf-8") as f:
            cookies[portal_name] = json.load(f)
    return cookies


def load_contacts(data_dir="data"):
    """Load existing contacts database."""
    contacts_file = Path(data_dir) / "contacts.json"
    if contacts_file.exists():
        with open(contacts_file, encoding="utf-8-sig") as f:
            return json.load(f)
    return {
        "last_updated": None,
        "contacts": {},       # keyed by listing_id
        "brokers": {},        # keyed by broker phone (dedup)
        "stats": {
            "total_extracted": 0,
            "phone_full": 0,
            "phone_masked": 0,
            "whatsapp_available": 0,
            "form_only": 0,
        }
    }


def save_contacts(contacts_db, data_dir="data"):
    """Save contacts database."""
    Path(data_dir).mkdir(exist_ok=True)
    contacts_file = Path(data_dir) / "contacts.json"
    contacts_db["last_updated"] = datetime.now().isoformat()
    with open(contacts_file, "w", encoding="utf-8") as f:
        json.dump(contacts_db, f, indent=2, ensure_ascii=False)


def load_published_listings(data_dir="data"):
    """Load the listings produced by scraper.py."""
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"rounds": []}


def get_all_listings(published):
    """Flatten all rounds into a single list of listings, most recent first."""
    all_listings = []
    for round_data in reversed(published.get("rounds", [])):
        for listing in round_data.get("listings", []):
            all_listings.append(listing)
    return all_listings


# ---------------------------------------------------------------------------
# Portal-specific contact extraction
# ---------------------------------------------------------------------------

def extract_batdongsan_contacts(page, listing_url, timeout=10000):
    """
    Extract contacts from a batdongsan.com.vn listing page.
    Requires authenticated session to click "Hiện số" for full phone.
    """
    result = {
        "broker_name": None,
        "broker_phone": None,
        "broker_phone_full": False,
        "whatsapp_url": None,
        "zalo_url": None,
        "messenger_url": None,
        "form_url": None,
        "broker_profile_url": None,
        "contact_method": None,
    }

    try:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(3000)  # Let dynamic content load

        content = page.content()

        # --- Broker name ---
        # Look for the agent name in the sidebar
        try:
            name_el = page.query_selector('a[href*="guru.batdongsan.com.vn/pa/"]')
            if name_el:
                result["broker_name"] = name_el.inner_text().strip()
                result["broker_profile_url"] = name_el.get_attribute("href")
        except Exception:
            pass

        # Fallback: extract from page text
        if not result["broker_name"]:
            name_match = re.search(
                r'(?:Liên hệ|liên hệ).*?(?:Mr|Ms|Anh|Chị|Mr\.|Ms\.)\s+([A-ZĐÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZĐÀ-Ỹ][a-zà-ỹ]+)*)',
                content
            )
            if name_match:
                result["broker_name"] = name_match.group(1).strip()

        # --- Try clicking "Hiện số" to reveal full phone ---
        try:
            # Multiple possible selectors for the phone reveal button
            reveal_selectors = [
                'text="Hiện số"',
                'button:has-text("Hiện số")',
                'a:has-text("Hiện số")',
                '[class*="phone"] [class*="show"]',
                '[class*="reveal"]',
                'span:has-text("Hiện số")',
            ]
            clicked = False
            for selector in reveal_selectors:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        clicked = True
                        page.wait_for_timeout(2000)  # Wait for phone to appear
                        break
                except Exception:
                    continue

            if clicked:
                # After clicking, look for the full phone number
                updated_content = page.content()
                # Full Vietnamese phone: 0XXX XXX XXXX or 0XXXXXXXXX
                phone_match = re.search(
                    r'(?:tel:|href="tel:)(\+?84\d{8,10}|0\d{9,10})',
                    updated_content
                )
                if phone_match:
                    result["broker_phone"] = normalize_phone(phone_match.group(1))
                    result["broker_phone_full"] = True
                else:
                    # Try finding phone in visible text after click
                    phone_match = re.search(
                        r'(0\d{2,3}[\s.]?\d{3}[\s.]?\d{3,4})',
                        updated_content
                    )
                    if phone_match:
                        phone_str = phone_match.group(1)
                        if '*' not in phone_str:
                            result["broker_phone"] = normalize_phone(phone_str)
                            result["broker_phone_full"] = True

        except Exception as e:
            print(f"      Phone reveal failed: {e}")

        # --- Fallback: extract masked phone ---
        if not result["broker_phone"]:
            masked_match = re.search(r'(0\d{2,3}[\s.]?\d{3}[\s.]\*{2,3})', content)
            if masked_match:
                result["broker_phone"] = masked_match.group(1).replace(" ", "")
                result["broker_phone_full"] = False

        # --- Phone from listing title/description/URL slug ---
        if not result["broker_phone_full"]:
            # Some brokers embed their full phone in the listing text
            text = page.inner_text("body")
            phone_in_text = re.findall(
                r'(?:liên hệ|LH|gọi|call|zalo)\s*:?\s*(0\d{2,3}[\s.]?\d{3}[\s.]?\d{3,4})',
                text, re.IGNORECASE
            )
            for p in phone_in_text:
                if '*' not in p:
                    result["broker_phone"] = normalize_phone(p)
                    result["broker_phone_full"] = True
                    break

            # Check URL slug for phone numbers
            url_phones = re.findall(r'(0\d{9,10})', listing_url.replace("-", ""))
            if url_phones:
                result["broker_phone"] = normalize_phone(url_phones[0])
                result["broker_phone_full"] = True

        # --- Zalo link ---
        zalo_match = re.search(r'(https?://(?:chat\.)?zalo\.me/\S+)', content)
        if zalo_match:
            result["zalo_url"] = zalo_match.group(1)

        # --- Determine contact method ---
        if result["broker_phone_full"]:
            result["contact_method"] = "whatsapp"  # We'll use WhatsApp with the full phone
        elif result["zalo_url"]:
            result["contact_method"] = "zalo"
        else:
            result["contact_method"] = "phone_masked"

    except Exception as e:
        print(f"      ERROR extracting batdongsan contacts: {e}")

    return result


def extract_dotproperty_contacts(page, listing_url, timeout=10000):
    """
    Extract contacts from a dotproperty.com.vn listing page.
    Requires authenticated session for full phone/WhatsApp.
    """
    result = {
        "broker_name": None,
        "broker_phone": None,
        "broker_phone_full": False,
        "whatsapp_url": None,
        "zalo_url": None,
        "messenger_url": None,
        "form_url": None,
        "broker_profile_url": None,
        "contact_method": None,
    }

    try:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(3000)

        content = page.content()

        # --- Broker name ---
        try:
            # dotproperty shows agent name prominently
            name_el = page.query_selector('[class*="agent-name"], [class*="AgentName"]')
            if name_el:
                result["broker_name"] = name_el.inner_text().strip()
        except Exception:
            pass

        if not result["broker_name"]:
            name_match = re.search(r'(?:Listed by|Agent|Contact)\s*:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', content)
            if name_match:
                result["broker_name"] = name_match.group(1).strip()

        # --- Try clicking Call/View Phone ---
        try:
            call_selectors = [
                'a:has-text("Call")',
                'button:has-text("Call")',
                '[class*="call"]',
                'img[alt*="Call"]',
                'a[href^="tel:"]',
            ]
            for selector in call_selectors:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue

            updated_content = page.content()

            # Look for tel: links
            tel_match = re.search(r'href="tel:(\+?\d{10,13})"', updated_content)
            if tel_match:
                result["broker_phone"] = normalize_phone(tel_match.group(1))
                result["broker_phone_full"] = True

        except Exception as e:
            print(f"      Phone click failed: {e}")

        # --- WhatsApp link ---
        wa_match = re.search(r'(https?://wa\.me/\d+)', content)
        if wa_match:
            result["whatsapp_url"] = wa_match.group(1)
            # Extract phone from wa.me link
            wa_phone = re.search(r'wa\.me/(\d+)', wa_match.group(1))
            if wa_phone:
                result["broker_phone"] = normalize_phone(wa_phone.group(1))
                result["broker_phone_full"] = True

        # --- Try clicking WhatsApp button ---
        if not result["whatsapp_url"]:
            try:
                wa_selectors = [
                    'a:has-text("Whatsapp")',
                    'a:has-text("WhatsApp")',
                    'img[alt*="hatsapp"]',  # Matches Whatsapp/WhatsApp
                    '[class*="whatsapp"]',
                ]
                for selector in wa_selectors:
                    try:
                        el = page.query_selector(selector)
                        if el:
                            href = el.get_attribute("href")
                            if href and "wa.me" in href:
                                result["whatsapp_url"] = href
                                wa_phone = re.search(r'wa\.me/(\d+)', href)
                                if wa_phone:
                                    result["broker_phone"] = normalize_phone(wa_phone.group(1))
                                    result["broker_phone_full"] = True
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        # --- Messenger link ---
        msg_match = re.search(r'(https?://m\.me/\S+|https?://(?:www\.)?facebook\.com/messages/\S+)', content)
        if msg_match:
            result["messenger_url"] = msg_match.group(1)

        # --- Inquiry form URL ---
        form_match = re.search(r'(https?://www\.dotproperty\.com\.vn/en/enquire/\S+)', content)
        if form_match:
            result["form_url"] = form_match.group(1)
        else:
            # Construct from listing URL
            listing_id_match = re.search(r'_(\d+)$', listing_url)
            if listing_id_match:
                result["form_url"] = f"https://www.dotproperty.com.vn/en/enquire/{listing_id_match.group(1)}"

        # --- Determine best contact method ---
        if result["whatsapp_url"]:
            result["contact_method"] = "whatsapp"
        elif result["broker_phone_full"]:
            result["contact_method"] = "whatsapp"
        elif result["form_url"]:
            result["contact_method"] = "form"
        elif result["messenger_url"]:
            result["contact_method"] = "messenger"
        else:
            result["contact_method"] = "form"

    except Exception as e:
        print(f"      ERROR extracting dotproperty contacts: {e}")

    return result


def extract_fazwaz_contacts(page, listing_url, timeout=10000):
    """
    Extract contacts from fazwaz.vn listing page.
    FazWaz only offers web forms — no direct phone/WhatsApp.
    """
    result = {
        "broker_name": None,
        "broker_phone": None,
        "broker_phone_full": False,
        "whatsapp_url": None,
        "zalo_url": None,
        "messenger_url": None,
        "form_url": listing_url,  # The listing itself has the form
        "broker_profile_url": None,
        "contact_method": "form",
    }

    try:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(3000)

        content = page.content()

        # --- Agent name ---
        try:
            name_el = page.query_selector('[class*="agent"] [class*="name"]')
            if name_el:
                result["broker_name"] = name_el.inner_text().strip()
        except Exception:
            pass

        # --- WhatsApp (some fazwaz listings have it) ---
        wa_match = re.search(r'(https?://wa\.me/\d+)', content)
        if wa_match:
            result["whatsapp_url"] = wa_match.group(1)
            wa_phone = re.search(r'wa\.me/(\d+)', wa_match.group(1))
            if wa_phone:
                result["broker_phone"] = normalize_phone(wa_phone.group(1))
                result["broker_phone_full"] = True
                result["contact_method"] = "whatsapp"

    except Exception as e:
        print(f"      ERROR extracting fazwaz contacts: {e}")

    return result


def extract_generic_contacts(page, listing_url, timeout=10000):
    """Fallback extractor for other portals (tranio, vietnam-real.estate, nhatot)."""
    result = {
        "broker_name": None,
        "broker_phone": None,
        "broker_phone_full": False,
        "whatsapp_url": None,
        "zalo_url": None,
        "messenger_url": None,
        "form_url": listing_url,
        "broker_profile_url": None,
        "contact_method": "form",
    }

    try:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(3000)

        content = page.content()

        # Generic phone extraction
        tel_match = re.search(r'href="tel:(\+?\d{10,13})"', content)
        if tel_match:
            result["broker_phone"] = normalize_phone(tel_match.group(1))
            result["broker_phone_full"] = True
            result["contact_method"] = "whatsapp"

        # Generic WhatsApp
        wa_match = re.search(r'(https?://wa\.me/\d+)', content)
        if wa_match:
            result["whatsapp_url"] = wa_match.group(1)
            result["contact_method"] = "whatsapp"

    except Exception as e:
        print(f"      ERROR extracting generic contacts: {e}")

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone(phone_str):
    """Normalize a Vietnamese phone number to +84XXXXXXXXX format."""
    phone = re.sub(r'[\s\-\.\(\)]', '', phone_str)
    if phone.startswith('0'):
        phone = '+84' + phone[1:]
    elif phone.startswith('84') and not phone.startswith('+84'):
        phone = '+' + phone
    elif not phone.startswith('+'):
        phone = '+84' + phone
    return phone


def get_portal_from_url(url):
    """Determine which portal a URL belongs to."""
    url_lower = url.lower()
    if 'batdongsan.com.vn' in url_lower:
        return 'batdongsan'
    elif 'dotproperty' in url_lower:
        return 'dotproperty'
    elif 'fazwaz' in url_lower:
        return 'fazwaz'
    elif 'tranio' in url_lower:
        return 'tranio'
    elif 'vietnam-real.estate' in url_lower:
        return 'vietnam-real-estate'
    elif 'nhatot' in url_lower:
        return 'nhatot'
    return 'unknown'


def get_extractor(portal):
    """Return the appropriate contact extraction function for a portal."""
    extractors = {
        'batdongsan': extract_batdongsan_contacts,
        'dotproperty': extract_dotproperty_contacts,
        'fazwaz': extract_fazwaz_contacts,
    }
    return extractors.get(portal, extract_generic_contacts)


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def run_contact_extraction(data_dir="data", cookies_dir="cookies", max_per_run=50):
    """
    Main entry point: load listings, extract contacts, save results.
    """
    from playwright.sync_api import sync_playwright

    print(f"\n{'='*60}")
    print(f"  Contact Extractor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    # Load existing data
    published = load_published_listings(data_dir)
    contacts_db = load_contacts(data_dir)
    all_listings = get_all_listings(published)

    print(f"Total listings in database: {len(all_listings)}")
    print(f"Existing contacts: {len(contacts_db['contacts'])}")

    # Find listings that don't have contacts yet
    pending = []
    for listing in all_listings:
        lid = listing.get("listing_id", "")
        if lid and lid not in contacts_db["contacts"]:
            pending.append(listing)

    # Prioritize: highest score first
    pending.sort(key=lambda x: x.get("score", 0), reverse=True)
    pending = pending[:max_per_run]

    print(f"Listings needing contact extraction: {len(pending)}")

    if not pending:
        print("No new listings to process. Done.")
        save_contacts(contacts_db, data_dir)
        return

    # Load cookies
    cookies_available = load_cookies(cookies_dir) if Path(cookies_dir).exists() else {}
    print(f"Cookie files loaded for: {list(cookies_available.keys()) or 'none'}")

    # Launch browser
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for portal_name, portal_cookies in cookies_available.items():
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
            )
            # Add cookies for this portal
            if portal_cookies:
                try:
                    context.add_cookies(portal_cookies)
                    print(f"  Loaded {len(portal_cookies)} cookies for {portal_name}")
                except Exception as e:
                    print(f"  WARNING: Failed to load cookies for {portal_name}: {e}")

            # Process listings for this portal
            portal_listings = [l for l in pending if get_portal_from_url(l.get("url", "")) == portal_name]
            if not portal_listings:
                context.close()
                continue

            page = context.new_page()
            extractor = get_extractor(portal_name)

            for i, listing in enumerate(portal_listings):
                lid = listing.get("listing_id", "")
                url = listing.get("url", "")
                score = listing.get("score", 0)

                print(f"\n  [{i+1}/{len(portal_listings)}] {portal_name} | score={score:.1f} | {url[:70]}")

                try:
                    contact_info = extractor(page, url)

                    # Store in contacts database
                    contacts_db["contacts"][lid] = {
                        "listing_id": lid,
                        "listing_url": url,
                        "listing_title": listing.get("title_original", listing.get("title", ""))[:100],
                        "listing_score": score,
                        "location": listing.get("location_key", ""),
                        "portal": portal_name,
                        "price_eur": listing.get("price_eur"),
                        "extracted_at": datetime.now().isoformat(),
                        **contact_info,
                        "outreach_status": "pending",  # pending / contacted / responded / meeting / rejected
                        "outreach_date": None,
                        "outreach_channel": None,
                        "response_date": None,
                        "response_notes": None,
                        "follow_up_dates": [],
                    }

                    # Update broker dedup index
                    if contact_info.get("broker_phone") and contact_info.get("broker_phone_full"):
                        phone = contact_info["broker_phone"]
                        if phone not in contacts_db["brokers"]:
                            contacts_db["brokers"][phone] = {
                                "name": contact_info.get("broker_name"),
                                "phone": phone,
                                "first_seen": datetime.now().isoformat(),
                                "listings": [lid],
                                "portal": portal_name,
                            }
                        else:
                            if lid not in contacts_db["brokers"][phone]["listings"]:
                                contacts_db["brokers"][phone]["listings"].append(lid)

                    # Update stats
                    contacts_db["stats"]["total_extracted"] += 1
                    if contact_info.get("broker_phone_full"):
                        contacts_db["stats"]["phone_full"] += 1
                    elif contact_info.get("broker_phone"):
                        contacts_db["stats"]["phone_masked"] += 1
                    if contact_info.get("whatsapp_url"):
                        contacts_db["stats"]["whatsapp_available"] += 1
                    if contact_info.get("contact_method") == "form":
                        contacts_db["stats"]["form_only"] += 1

                    method = contact_info.get("contact_method", "unknown")
                    phone_display = contact_info.get("broker_phone", "no phone")
                    name_display = contact_info.get("broker_name", "unknown")
                    print(f"    ✓ {name_display} | {phone_display} | method: {method}")

                    time.sleep(1)  # Rate limiting

                except Exception as e:
                    print(f"    ✗ Failed: {e}")
                    # Store failure so we don't retry endlessly
                    contacts_db["contacts"][lid] = {
                        "listing_id": lid,
                        "listing_url": url,
                        "portal": portal_name,
                        "extracted_at": datetime.now().isoformat(),
                        "extraction_error": str(e),
                        "outreach_status": "error",
                    }

            page.close()
            context.close()

        # Handle listings from portals with NO cookies (still extract what we can)
        uncookied_listings = [
            l for l in pending
            if get_portal_from_url(l.get("url", "")) not in cookies_available
            and l.get("listing_id", "") not in contacts_db["contacts"]
        ]

        if uncookied_listings:
            print(f"\n  Processing {len(uncookied_listings)} listings without cookies...")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            for i, listing in enumerate(uncookied_listings):
                lid = listing.get("listing_id", "")
                url = listing.get("url", "")
                portal = get_portal_from_url(url)
                score = listing.get("score", 0)

                print(f"\n  [{i+1}/{len(uncookied_listings)}] {portal} (no cookies) | score={score:.1f}")

                try:
                    extractor = get_extractor(portal)
                    contact_info = extractor(page, url)

                    contacts_db["contacts"][lid] = {
                        "listing_id": lid,
                        "listing_url": url,
                        "listing_title": listing.get("title_original", listing.get("title", ""))[:100],
                        "listing_score": score,
                        "location": listing.get("location_key", ""),
                        "portal": portal,
                        "price_eur": listing.get("price_eur"),
                        "extracted_at": datetime.now().isoformat(),
                        **contact_info,
                        "outreach_status": "pending",
                        "outreach_date": None,
                        "outreach_channel": None,
                        "response_date": None,
                        "response_notes": None,
                        "follow_up_dates": [],
                        "no_cookies": True,
                    }

                    contacts_db["stats"]["total_extracted"] += 1
                    method = contact_info.get("contact_method", "unknown")
                    print(f"    ✓ method: {method} (limited — no cookies)")

                    time.sleep(1)

                except Exception as e:
                    print(f"    ✗ Failed: {e}")

            page.close()
            context.close()

        browser.close()

    # Save results
    save_contacts(contacts_db, data_dir)

    # Print summary
    stats = contacts_db["stats"]
    print(f"\n{'='*60}")
    print(f"  Extraction Complete")
    print(f"  Total contacts: {stats['total_extracted']}")
    print(f"  Full phones: {stats['phone_full']}")
    print(f"  Masked phones: {stats['phone_masked']}")
    print(f"  WhatsApp available: {stats['whatsapp_available']}")
    print(f"  Form only: {stats['form_only']}")
    print(f"  Unique brokers: {len(contacts_db['brokers'])}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", "data")
    cookies_dir = os.environ.get("COOKIES_DIR", "cookies")
    max_per_run = int(os.environ.get("MAX_CONTACTS_PER_RUN", "50"))

    run_contact_extraction(
        data_dir=data_dir,
        cookies_dir=cookies_dir,
        max_per_run=max_per_run,
    )
