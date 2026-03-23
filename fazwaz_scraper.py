#!/usr/bin/env python3
"""
FazWaz Property Scraper — Playwright Edition
FazWaz is a JS SPA that Firecrawl can't scrape.
This script uses Playwright to render pages and extract listings.

Runs as an additional step in GitHub Actions after the main scraper.
"""

import json
import re
import os
import time
from datetime import datetime
from pathlib import Path


FAZWAZ_TARGETS = [
    {"location_key": "phu_quoc", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/kien-giang/phu-quoc", "min_br": 1, "max_br": 1},
    {"location_key": "quy_nhon", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/binh-dinh/quy-nhon", "min_br": 2, "max_br": 99},
    {"location_key": "da_lat", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/lam-dong/da-lat", "min_br": 1, "max_br": 99},
    {"location_key": "con_dao", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/ba-ria-vung-tau", "min_br": 1, "max_br": 99},
]

BUDGET_MAX_EUR = 150000
VND_PER_EUR = 27000


def dismiss_popups(page):
    """Dismiss all cookie/consent popups on FazWaz."""
    selectors = [
        'button:has-text("DECLINE ALL")',
        'button:has-text("REJECT ALL")',
        'button:has-text("Decline All")',
        'button:has-text("Reject All")',
        'button:has-text("Accept")',
        'button:has-text("AGREE")',
        'button:has-text("OK")',
        'button:has-text("SAVE & EXIT")',
        'button:has-text("Save & Exit")',
        '[class*="cookie"] button',
        '[class*="consent"] button',
        '[class*="privacy"] button',
    ]
    dismissed = 0
    for selector in selectors:
        try:
            els = page.query_selector_all(selector)
            for el in els:
                if el.is_visible():
                    el.click()
                    dismissed += 1
                    page.wait_for_timeout(500)
        except Exception:
            pass
    # Also try pressing Escape
    if dismissed == 0:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    return dismissed


def extract_listings_from_search(page, target_url, location_key, min_br, max_br):
    """Navigate to FazWaz search page and extract all listing URLs."""
    print(f"  Loading {target_url}...")
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  ERROR loading page: {e}")
        return []

    # Wait longer for JS to render
    page.wait_for_timeout(8000)

    # Dismiss cookie popups aggressively
    dismiss_popups(page)
    page.wait_for_timeout(2000)
    dismiss_popups(page)

    # Scroll to trigger lazy loading
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(800)

    # Scroll back up
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    # Extract listing URLs
    listing_urls = page.evaluate("""
        () => {
            var urls = new Set();
            document.querySelectorAll('a[href*="/property-sales/"]').forEach(a => {
                if (a.href.match(/[uU]\\d{4,}/)) urls.add(a.href);
            });
            document.querySelectorAll('a[href*="/property/"]').forEach(a => {
                if (a.href.match(/\\d{6,}/)) urls.add(a.href);
            });
            // Also try data-href or onclick patterns
            document.querySelectorAll('[data-href*="fazwaz"]').forEach(el => {
                if (el.dataset.href.match(/[uU]\\d{4,}/)) urls.add(el.dataset.href);
            });
            return [...urls];
        }
    """)

    # Deduplicate by listing ID
    seen_ids = set()
    unique_urls = []
    for url in listing_urls:
        id_match = re.search(r'[uU](\d{4,})', url)
        if id_match:
            lid = id_match.group(1)
            if lid not in seen_ids:
                seen_ids.add(lid)
                unique_urls.append(url)
        else:
            unique_urls.append(url)

    print(f"  Found {len(unique_urls)} listing URLs")
    return unique_urls


def parse_from_title(title):
    """Extract bedrooms, price, location from FazWaz page title.
    Example: '1 Bedroom Condo for Sale in Nhon Ly, Binh Dinh for 139,000,000 ₫ | U2121608'
    Also handles: '...for €4,570 | U2121608' (EUR format)
    """
    result = {}

    # Bedrooms
    br_match = re.search(r'(\d+)\s*Bedroom', title, re.IGNORECASE)
    if br_match:
        result["bedrooms"] = int(br_match.group(1))

    # Price EUR (€ symbol)
    eur_match = re.search(r'€([\d,]+)', title)
    if eur_match:
        try:
            result["price_eur"] = int(eur_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Price VND — raw format "NUMBER ₫" (number before symbol, no unit suffix)
    # This is the current FazWaz title format: "for 139,000,000 ₫ |"
    if "price_eur" not in result:
        vnd_raw_match = re.search(r'([\d,]+)\s*₫', title)
        if vnd_raw_match:
            try:
                val = int(vnd_raw_match.group(1).replace(",", ""))
                if val > 1_000_000:  # sanity check — must be at least 1M VND
                    result["price_vnd"] = val
                    result["price_eur"] = int(val / VND_PER_EUR)
            except ValueError:
                pass

    # Price VND — "₫ NUMBER billion/million" format (symbol before number, with unit)
    if "price_vnd" not in result:
        vnd_unit_match = re.search(r'₫\s*([\d,.]+)\s*(billion|million|tỷ|triệu)', title, re.IGNORECASE)
        if vnd_unit_match:
            try:
                val = float(vnd_unit_match.group(1).replace(",", ""))
                unit = vnd_unit_match.group(2).lower()
                if unit in ("billion", "tỷ"):
                    result["price_vnd"] = int(val * 1_000_000_000)
                    if "price_eur" not in result:
                        result["price_eur"] = int(val * 1_000_000_000 / VND_PER_EUR)
                elif unit in ("million", "triệu"):
                    result["price_vnd"] = int(val * 1_000_000)
                    if "price_eur" not in result:
                        result["price_eur"] = int(val * 1_000_000 / VND_PER_EUR)
            except ValueError:
                pass

    # Property type
    if "Condo" in title:
        result["type"] = "Condo"
    elif "Apartment" in title:
        result["type"] = "Apartment"
    elif "Villa" in title:
        result["type"] = "Villa"

    # Location from title
    loc_match = re.search(r'in\s+(.+?)(?:\s+for\s+|$)', title)
    if loc_match:
        result["location_text"] = loc_match.group(1).strip()

    return result


def parse_listing_page(page, url, location_key):
    """Visit a FazWaz listing and extract property data."""
    listing = {
        "url": url,
        "portal": "fazwaz",
        "location_key": location_key,
        "title": "",
        "title_original": "",
        "price_vnd": None,
        "price_eur": None,
        "bedrooms": None,
        "bathrooms": None,
        "area_sqm": None,
        "price_per_sqm_eur": None,
        "developer": None,
        "legal_status": None,
        "furnishing": None,
        "listing_id": None,
    }

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(5000)

        dismiss_popups(page)

        # Extract listing ID from URL
        id_match = re.search(r'[uU](\d{4,})', url)
        if id_match:
            listing["listing_id"] = f"fazwaz_{id_match.group(1)}"

        # Get page title — this is the most reliable data source on FazWaz
        title = page.title() or ""
        listing["title"] = title
        listing["title_original"] = title

        # Parse data from title first (most reliable)
        title_data = parse_from_title(title)
        if title_data.get("bedrooms"):
            listing["bedrooms"] = title_data["bedrooms"]
        if title_data.get("price_eur"):
            listing["price_eur"] = title_data["price_eur"]
        if title_data.get("price_vnd"):
            listing["price_vnd"] = title_data["price_vnd"]

        # Try extracting more from the rendered page
        try:
            data = page.evaluate("""
                () => {
                    var result = {};
                    var bodyText = document.body.innerText || '';

                    // Only parse if page actually rendered (more than just nav)
                    if (bodyText.length < 500) return result;

                    // Price — try EUR first, then VND
                    var eurMatch = bodyText.match(/€([\\d,]+)/);
                    if (eurMatch) result.price_eur = eurMatch[1].replace(/,/g, '');

                    // Price VND — try dedicated price element first (avoids matching price/sqm)
                    if (!result.price_eur) {
                        var priceEl = document.querySelector('[class*="sale-price"], [class*="unit-price"], [class*="price-tag"]');
                        if (priceEl) {
                            var ptxt = priceEl.innerText || '';
                            var pelMatch = ptxt.match(/([\\d,]+)\\s*₫/);
                            if (pelMatch) result.price_vnd = parseInt(pelMatch[1].replace(/,/g, ''));
                        }
                        // Fallback: "for X ₫" pattern in body text (skips price/sqm which has "/SqM" after)
                        if (!result.price_vnd) {
                            var forVndMatch = bodyText.match(/for\\s+([\\d,]+)\\s*₫/i);
                            if (forVndMatch) result.price_vnd = parseInt(forVndMatch[1].replace(/,/g, ''));
                        }
                        if (result.price_vnd) {
                            result.price_eur = Math.round(result.price_vnd / 27000).toString();
                        }
                    }

                    // Bedrooms
                    var brMatch = bodyText.match(/(\\d+)\\s*(?:Bedroom|BR|Bed)/i);
                    if (brMatch) result.bedrooms = parseInt(brMatch[1]);

                    // Bathrooms
                    var bathMatch = bodyText.match(/(\\d+)\\s*(?:Bathroom|Bath)/i);
                    if (bathMatch) result.bathrooms = parseInt(bathMatch[1]);

                    // Area
                    var areaMatch = bodyText.match(/(\\d+(?:\\.\\d+)?)\\s*(?:SqM|m²|sqm)/i);
                    if (areaMatch) result.area = parseFloat(areaMatch[1]);

                    // Foreign quota
                    if (bodyText.includes('Foreign Quota')) result.foreign_ok = true;

                    // Project name
                    var projMatch = bodyText.match(/(?:Project|at)\\s*:\\s*(.+?)(?:\\n|$)/i);
                    if (projMatch) result.project = projMatch[1].trim().substring(0, 60);

                    // WhatsApp
                    var waLink = document.querySelector('a[href*="wa.me"]');
                    if (waLink) result.whatsapp = waLink.href;

                    // Agent
                    var agentEl = document.querySelector('[class*="agent-name"], [class*="AgentName"]');
                    if (agentEl) result.agent = agentEl.innerText.trim().substring(0, 60);

                    return result;
                }
            """)

            # Fill in any data not already from title
            if not listing["price_eur"] and data.get("price_eur"):
                try:
                    listing["price_eur"] = int(data["price_eur"])
                except (ValueError, TypeError):
                    pass
            if not listing["price_vnd"] and data.get("price_vnd"):
                try:
                    listing["price_vnd"] = int(data["price_vnd"])
                    if not listing["price_eur"]:
                        listing["price_eur"] = int(listing["price_vnd"] / VND_PER_EUR)
                except (ValueError, TypeError):
                    pass
            if not listing["bedrooms"] and data.get("bedrooms"):
                listing["bedrooms"] = data["bedrooms"]
            if data.get("bathrooms"):
                listing["bathrooms"] = data["bathrooms"]
            if data.get("area"):
                listing["area_sqm"] = data["area"]
            if data.get("project"):
                listing["developer"] = data["project"]
            if data.get("foreign_ok"):
                listing["legal_status"] = "foreign_eligible"
            if data.get("agent"):
                listing["broker_name"] = data["agent"]
            if data.get("whatsapp"):
                listing["whatsapp_url"] = data["whatsapp"]

        except Exception as e:
            print(f"    JS evaluate failed (using title data): {e}")

        # Calculate derived fields
        if listing["price_eur"] and not listing["price_vnd"]:
            listing["price_vnd"] = listing["price_eur"] * VND_PER_EUR
        if listing["price_eur"] and listing["area_sqm"]:
            listing["price_per_sqm_eur"] = round(listing["price_eur"] / listing["area_sqm"])

        if not listing["listing_id"]:
            listing["listing_id"] = f"fazwaz_{abs(hash(url)) % 100000000}"

    except Exception as e:
        print(f"    ERROR parsing {url[:60]}: {e}")

    return listing


def run_fazwaz_scraper(data_dir="data", max_listings_per_target=15):
    """Main entry point."""
    from playwright.sync_api import sync_playwright

    print(f"\n{'='*60}")
    print(f"  FazWaz Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, "r", encoding="utf-8-sig") as f:
            published = json.load(f)
    else:
        published = {"rounds": []}

    existing_ids = set()
    for round_data in published.get("rounds", []):
        for listing in round_data.get("listings", []):
            existing_ids.add(listing.get("listing_id", ""))

    all_new_listings = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        for target in FAZWAZ_TARGETS:
            loc = target["location_key"]
            url = target["url"]
            min_br = target["min_br"]
            max_br = target["max_br"]

            print(f"\n--- {loc.upper()} ({url}) ---")

            listing_urls = extract_listings_from_search(page, url, loc, min_br, max_br)
            listing_urls = listing_urls[:max_listings_per_target]

            for i, lurl in enumerate(listing_urls):
                id_match = re.search(r'[uU](\d{4,})', lurl)
                lid = f"fazwaz_{id_match.group(1)}" if id_match else None
                if lid and lid in existing_ids:
                    print(f"  [{i+1}/{len(listing_urls)}] Skip (already seen): {lurl[-30:]}")
                    continue

                print(f"  [{i+1}/{len(listing_urls)}] Parsing: {lurl[-50:]}")
                listing = parse_listing_page(page, lurl, loc)

                # Apply filters
                if listing.get("price_eur") and listing["price_eur"] > BUDGET_MAX_EUR:
                    print(f"    Skip: over budget (EUR {listing['price_eur']})")
                    continue

                br = listing.get("bedrooms")
                if br is not None and (br < min_br or br > max_br):
                    print(f"    Skip: {br}BR not in range {min_br}-{max_br}")
                    continue

                if listing.get("listing_id"):
                    all_new_listings.append(listing)
                    price_display = f"EUR {listing['price_eur']}" if listing.get("price_eur") else "price unknown"
                    br_display = f"{listing.get('bedrooms', '?')}BR"
                    area_display = f"{listing.get('area_sqm', '?')}m2"
                    print(f"    OK: {listing['title'][:50]} | {price_display} | {br_display} | {area_display}")
                    existing_ids.add(listing["listing_id"])

                time.sleep(1)

        page.close()
        context.close()
        browser.close()

    print(f"\n{'='*60}")
    print(f"  FazWaz Results: {len(all_new_listings)} new listings")
    print(f"{'='*60}\n")

    if all_new_listings:
        round_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "source": "fazwaz_playwright",
            "total_searched": len(FAZWAZ_TARGETS),
            "new_found": len(all_new_listings),
            "published_count": len(all_new_listings),
            "listings": all_new_listings,
        }
        published.setdefault("rounds", []).append(round_data)

        Path(data_dir).mkdir(exist_ok=True)
        with open(pub_file, "w", encoding="utf-8") as f:
            json.dump(published, f, indent=2, ensure_ascii=False)
        print(f"Saved to {pub_file}")

    return all_new_listings


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", "data")
    max_per = int(os.environ.get("FAZWAZ_MAX_PER_TARGET", "15"))
    run_fazwaz_scraper(data_dir=data_dir, max_listings_per_target=max_per)
