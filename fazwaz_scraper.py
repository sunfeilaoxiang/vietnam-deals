#!/usr/bin/env python3
"""
FazWaz Property Scraper — Playwright Edition
FazWaz is a JS SPA that Firecrawl can't scrape.
This script uses Playwright to render pages and extract listings.

Runs as an additional step in GitHub Actions after the main scraper.
Outputs listings in the same format as scraper.py for merging.
"""

import json
import re
import os
import time
from datetime import datetime
from pathlib import Path


# FazWaz search targets (same cities as main scraper)
FAZWAZ_TARGETS = [
    {"location_key": "phu_quoc", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/kien-giang/phu-quoc", "min_br": 1, "max_br": 1},
    {"location_key": "quy_nhon", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/binh-dinh/quy-nhon", "min_br": 2, "max_br": 99},
    {"location_key": "da_lat", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/lam-dong/da-lat", "min_br": 1, "max_br": 99},
    {"location_key": "con_dao", "url": "https://www.fazwaz.vn/condo-for-sale/vietnam/ba-ria-vung-tau", "min_br": 1, "max_br": 99},
]

BUDGET_MAX_EUR = 150000
VND_PER_EUR = 27000


def extract_listings_from_search(page, target_url, location_key, min_br, max_br):
    """Navigate to FazWaz search page and extract all listing data."""
    listings = []

    print(f"  Loading {target_url}...")
    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)  # Let React render

    # Dismiss cookie popups
    for selector in ['button:has-text("DECLINE ALL")', 'button:has-text("REJECT ALL")', 'button:has-text("Accept")']:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

    # Scroll to load all listings (FazWaz may lazy-load)
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(1000)

    # Extract listing URLs from the rendered page
    listing_urls = page.evaluate("""
        () => {
            var urls = new Set();
            document.querySelectorAll('a[href*="/property-sales/"]').forEach(a => {
                if (a.href.match(/u\\d{4,}/)) urls.add(a.href);
            });
            // Also check for other listing URL patterns
            document.querySelectorAll('a[href*="/property/"]').forEach(a => {
                if (a.href.match(/\\d{6,}/)) urls.add(a.href);
            });
            return [...urls];
        }
    """)

    print(f"  Found {len(listing_urls)} listing URLs")

    # If no listing URLs found via links, try extracting data directly from cards
    if not listing_urls:
        print("  Trying card extraction...")
        card_data = page.evaluate("""
            () => {
                var cards = [];
                // Try various card selectors
                var allText = document.body.innerText;
                // Split by price patterns to find card boundaries
                var chunks = allText.split(/€[\\d,]+/);
                return {textLength: allText.length, chunks: chunks.length, sample: allText.substring(0, 1000)};
            }
        """)
        print(f"  Page text: {card_data.get('textLength', 0)} chars")

    return listing_urls


def parse_listing_page(page, url, location_key):
    """Visit an individual FazWaz listing and extract property data."""
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
        page.wait_for_timeout(3000)

        # Dismiss popups
        for selector in ['button:has-text("DECLINE ALL")', 'button:has-text("REJECT ALL")', 'button:has-text("Accept")']:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # Extract listing ID from URL
        id_match = re.search(r'[uU](\d{4,})', url)
        if id_match:
            listing["listing_id"] = f"fazwaz_{id_match.group(1)}"

        # Get page title
        title = page.title()
        listing["title"] = title
        listing["title_original"] = title

        # Extract structured data from page
        data = page.evaluate("""
            () => {
                var result = {};

                // Title
                var h1 = document.querySelector('h1');
                if (h1) result.title = h1.innerText.trim();

                // Price - look for EUR price
                var priceEls = document.querySelectorAll('[class*="price"], [class*="Price"]');
                priceEls.forEach(el => {
                    var text = el.innerText;
                    var eurMatch = text.match(/€([\\d,]+)/);
                    if (eurMatch) result.price_eur = eurMatch[1].replace(/,/g, '');
                    var vndMatch = text.match(/₫([\\d,.]+)/);
                    if (vndMatch) result.price_vnd = vndMatch[1].replace(/,/g, '');
                });

                // Also search full page text for price
                var bodyText = document.body.innerText;
                if (!result.price_eur) {
                    var eurMatch = bodyText.match(/€([\\d,]+)/);
                    if (eurMatch) result.price_eur = eurMatch[1].replace(/,/g, '');
                }

                // Bedrooms, bathrooms, area
                var brMatch = bodyText.match(/(\\d+)\\s*(?:Bedroom|BR|Bed)/i);
                if (brMatch) result.bedrooms = parseInt(brMatch[1]);

                var bathMatch = bodyText.match(/(\\d+)\\s*(?:Bathroom|Bath)/i);
                if (bathMatch) result.bathrooms = parseInt(bathMatch[1]);

                var areaMatch = bodyText.match(/(\\d+(?:\\.\\d+)?)\\s*(?:SqM|m²|sqm)/i);
                if (areaMatch) result.area = parseFloat(areaMatch[1]);

                // Developer/project
                var projEl = document.querySelector('[class*="project"], [class*="Project"]');
                if (projEl) result.project = projEl.innerText.trim().substring(0, 60);

                // Foreign quota tag
                if (bodyText.includes('Foreign Quota')) result.foreign_ok = true;

                // Floor
                var floorMatch = bodyText.match(/Floor\\s*(\\d+)/i);
                if (floorMatch) result.floor = parseInt(floorMatch[1]);

                // Contact info
                var contactEl = document.querySelector('[class*="agent"], [class*="Agent"]');
                if (contactEl) result.agent = contactEl.innerText.trim().substring(0, 60);

                // WhatsApp
                var waLink = document.querySelector('a[href*="wa.me"]');
                if (waLink) result.whatsapp = waLink.href;

                // Form URL
                result.form_url = window.location.href;

                return result;
            }
        """)

        if data.get("title"):
            listing["title"] = data["title"]
            listing["title_original"] = data["title"]

        if data.get("price_eur"):
            try:
                listing["price_eur"] = int(data["price_eur"])
                listing["price_vnd"] = listing["price_eur"] * VND_PER_EUR
            except (ValueError, TypeError):
                pass

        if data.get("bedrooms"):
            listing["bedrooms"] = data["bedrooms"]
        if data.get("bathrooms"):
            listing["bathrooms"] = data["bathrooms"]
        if data.get("area"):
            listing["area_sqm"] = data["area"]
            if listing["price_eur"] and listing["area_sqm"]:
                listing["price_per_sqm_eur"] = round(listing["price_eur"] / listing["area_sqm"])

        if data.get("project"):
            listing["developer"] = data["project"]
        if data.get("foreign_ok"):
            listing["legal_status"] = "foreign_eligible"
        if data.get("agent"):
            listing["broker_name"] = data["agent"]
        if data.get("whatsapp"):
            listing["whatsapp_url"] = data["whatsapp"]

        if not listing["listing_id"]:
            listing["listing_id"] = f"fazwaz_{hash(url) % 100000000}"

    except Exception as e:
        print(f"    ERROR parsing {url[:60]}: {e}")

    return listing


def run_fazwaz_scraper(data_dir="data", max_listings_per_target=15):
    """Main entry point for FazWaz scraping."""
    from playwright.sync_api import sync_playwright

    print(f"\n{'='*60}")
    print(f"  FazWaz Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    # Load existing published listings to avoid duplicates
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, "r", encoding="utf-8-sig") as f:
            published = json.load(f)
    else:
        published = {"rounds": []}

    # Collect existing listing IDs
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

            # Get listing URLs from search page
            listing_urls = extract_listings_from_search(page, url, loc, min_br, max_br)

            # Limit per target
            listing_urls = listing_urls[:max_listings_per_target]

            # Parse each listing
            for i, lurl in enumerate(listing_urls):
                # Check for duplicate
                id_match = re.search(r'[uU](\d{4,})', lurl)
                lid = f"fazwaz_{id_match.group(1)}" if id_match else None
                if lid and lid in existing_ids:
                    print(f"  [{i+1}/{len(listing_urls)}] Skip (already seen): {lurl[:60]}")
                    continue

                print(f"  [{i+1}/{len(listing_urls)}] Parsing: {lurl[:60]}")
                listing = parse_listing_page(page, lurl, loc)

                # Apply filters
                if listing.get("price_eur") and listing["price_eur"] > BUDGET_MAX_EUR:
                    print(f"    Skip: over budget (€{listing['price_eur']})")
                    continue

                br = listing.get("bedrooms")
                if br and (br < min_br or br > max_br):
                    print(f"    Skip: {br}BR not in range {min_br}-{max_br}")
                    continue

                if listing.get("listing_id"):
                    all_new_listings.append(listing)
                    price_display = f"€{listing['price_eur']}" if listing.get("price_eur") else "price unknown"
                    print(f"    OK: {listing['title'][:50]} | {price_display} | {listing.get('bedrooms', '?')}BR")
                    existing_ids.add(listing["listing_id"])

                time.sleep(1)  # Rate limiting

        page.close()
        context.close()
        browser.close()

    print(f"\n{'='*60}")
    print(f"  FazWaz Results: {len(all_new_listings)} new listings")
    print(f"{'='*60}\n")

    if all_new_listings:
        # Add to published listings as a new round
        round_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "source": "fazwaz_playwright",
            "total_searched": sum(1 for _ in FAZWAZ_TARGETS),
            "new_found": len(all_new_listings),
            "published_count": len(all_new_listings),
            "listings": all_new_listings,
        }
        published.setdefault("rounds", []).append(round_data)

        # Save
        Path(data_dir).mkdir(exist_ok=True)
        with open(pub_file, "w", encoding="utf-8") as f:
            json.dump(published, f, indent=2, ensure_ascii=False)
        print(f"Saved to {pub_file}")

    return all_new_listings


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", "data")
    max_per = int(os.environ.get("FAZWAZ_MAX_PER_TARGET", "15"))
    run_fazwaz_scraper(data_dir=data_dir, max_listings_per_target=max_per)
