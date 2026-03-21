"""
Vietnam Property Scraper — Firecrawl Edition
Scrapes property portals directly using Firecrawl API to extract
individual listing data with real URLs, prices, and property details.
"""

import json
import re
import hashlib
import time
import os
import urllib.request
import urllib.parse
import urllib.error
import ssl
from datetime import datetime
from pathlib import Path


def _clean_number(s):
    """Clean a number string that may use dots or commas as thousand separators."""
    s = s.strip()
    s = re.sub(r'[^\d.,-]', '', s)
    if not s or not re.search(r'\d', s):
        return 0.0
    try:
        if s.count('.') >= 2:
            return float(s.replace('.', ''))
        if s.count(',') >= 2:
            return float(s.replace(',', ''))
        if ',' in s and re.search(r',\d{3}$', s):
            return float(s.replace(',', ''))
        if '.' in s and re.search(r'\.\d{3}$', s):
            return float(s.replace('.', ''))
        return float(s.replace(',', ''))
    except ValueError:
        return 0.0


def load_config(config_path="config.json"):
    with open(config_path, encoding='utf-8-sig') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Firecrawl API
# ---------------------------------------------------------------------------

def firecrawl_scrape(url, api_key, formats=None, timeout=60):
    """
    Scrape a single URL via Firecrawl v1 and return the response data.
    Default format: markdown + links.  Costs 1 credit per call.
    """
    if formats is None:
        formats = ["markdown", "links"]

    payload = json.dumps({
        "url": url,
        "formats": formats,
        "timeout": 30000,
        "waitFor": 3000,
    }).encode()

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v1/scrape",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            if data.get("success"):
                return data.get("data", {})
            else:
                print(f"    Firecrawl error: {data.get('error', 'unknown')}")
                return {}
    except Exception as e:
        print(f"    Firecrawl request failed for {url}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Listing-type filters
# ---------------------------------------------------------------------------

# Vietnamese terms for non-apartment property types to SKIP
LAND_SKIP_TERMS = [
    'bán đất', 'ban dat', 'đất nền', 'dat nen', 'đất thổ', 'dat tho',
    'land for sale', 'đất đẹp', 'lô đất', 'lo dat',
    'biệt thự', 'biet thu', 'villa for sale',
    'nhà riêng', 'nha rieng', 'nhà phố', 'nha pho',
    'shophouse', 'shop house', 'townhouse', 'town house',
    'liền kề', 'lien ke', 'song lập', 'song lap',
    'warehouse', 'kho xưởng', 'factory',
]

# Price range filter text to skip (batdongsan sidebar filters)
PRICE_RANGE_SKIP = [
    'dưới 500', 'duoi 500', '500 - 800', '800 triệu - 1',
    '1 - 2 tỷ', '2 - 3 tỷ', '3 - 5 tỷ', '5 - 7 tỷ',
    '7 - 10 tỷ', '10 - 20 tỷ', '20 - 30 tỷ', '30 - 40 tỷ',
    '40 - 60 tỷ', 'trên 60 tỷ', 'tren 60',
]


def _is_apartment_listing(block, title):
    """Check if this block is about an apartment/condo, not land or villa."""
    text = f"{block} {title}".lower()

    # Skip if it's clearly land/villa/shophouse
    for term in LAND_SKIP_TERMS:
        if term in text:
            # But allow if it also mentions apartment/condo
            if any(apt in text for apt in ['căn hộ', 'can ho', 'apartment', 'condo', 'chung cư', 'chung cu']):
                continue
            return False

    # Skip price range filter blocks
    for term in PRICE_RANGE_SKIP:
        if term in text and len(block.strip()) < 100:
            return False

    return True


# ---------------------------------------------------------------------------
# Parsing listings from scraped pages
# ---------------------------------------------------------------------------

def parse_listings_from_page(page_data, portal_name, location_key, base_url, config):
    """
    Parse individual property listings from Firecrawl markdown + links output.
    Returns a list of listing dicts.
    """
    markdown = page_data.get("markdown", "")
    links = page_data.get("links", [])

    if not markdown:
        return []

    vnd_per_eur = config.get("vnd_per_eur", 27000)
    budget_max = config.get("budget_max_eur", 138000)
    listings = []

    # Collect all links that look like individual listing pages
    listing_links = []
    for link in links:
        url = link if isinstance(link, str) else link.get("url", link.get("href", ""))
        if not url:
            continue
        url_lower = url.lower()
        if any(skip in url_lower for skip in [
            '/tag/', '/tags/', '/category/', '/search', '/tim-kiem',
            'apartments-for-sale', 'condos-for-sale', 'property-for-sale',
            'properties-for-sale', '/for-rent', '/cho-thue',
            '/login', '/register', '/about', '/contact',
            'facebook.com', 'youtube.com', 'twitter.com', 'instagram.com',
            'javascript:', 'mailto:', '#', '/gia-tu-', '/gia-duoi-',
            'ban-dat-', 'ban-nha-rieng', 'ban-nha-biet-thu',
        ]):
            continue
        if _is_individual_listing_url(url_lower, portal_name):
            listing_links.append(url)

    # Split markdown into blocks per listing
    blocks = re.split(r'\n(?=#{1,3}\s|\*\*\[|\[\!\[|---\n|___\n|\* \*\*|\[!\[)', markdown)

    seen_urls = set()
    for block in blocks:
        try:
            if len(block.strip()) < 30:
                continue

            title = _extract_title_from_block(block)
            if not title or len(title) < 5:
                continue

            # Skip non-apartment listings
            if not _is_apartment_listing(block, title):
                print(f"    Skipped (not apartment): {title[:50]}")
                continue

            price_eur = extract_price(block, vnd_per_eur)
            if not price_eur:
                continue

            # Skip if way over budget (>3x) — likely bad parse
            if price_eur > budget_max * 3:
                continue

            # Find a listing link
            listing_url = _find_listing_url_in_block(block, listing_links, base_url)
            if not listing_url:
                continue

            # Deduplicate within page
            if listing_url in seen_urls:
                continue
            seen_urls.add(listing_url)

            size_sqm = extract_size(block)
            bedrooms = extract_bedrooms(block)
            bathrooms = extract_bathrooms(block)
            developer = extract_developer(block, config.get('known_developers', {}))
            legal_status = extract_legal_status(block)
            furnishing = extract_furnishing(block)

            # Translate title to Russian
            title_ru = translate_to_russian(title) if not is_mostly_ascii(title) else title
            desc_snippet = block[:300].strip()
            desc_ru = translate_to_russian(desc_snippet) if not is_mostly_ascii(desc_snippet) else desc_snippet

            listing = {
                'title': title_ru,
                'title_original': title,
                'url': listing_url,
                'portal': portal_name,
                'location_key': location_key,
                'price_eur': price_eur,
                'price_raw': extract_raw_price(block),
                'size_sqm': size_sqm,
                'bedrooms': bedrooms,
                'bathrooms': bathrooms,
                'developer': developer,
                'legal_status': legal_status,
                'furnishing': furnishing,
                'description': desc_ru,
                'description_original': desc_snippet,
                'sea_proximity': None,
                'found_date': datetime.now().strftime('%Y-%m-%d'),
                'source_snippet': desc_ru[:300],
            }
            listing['listing_id'] = generate_listing_id(listing)
            listings.append(listing)
        except Exception as e:
            print(f"    WARNING: Error parsing block: {e}")
            continue

    return listings


def _is_individual_listing_url(url_lower, portal_name):
    """Check if a URL looks like an individual property listing."""
    # batdongsan: individual listings have prXXXXX or end in .html
    if 'batdongsan.com.vn' in url_lower:
        return bool(re.search(r'pr\d{5,}|\.html', url_lower))
    # dotproperty: listings have _NNNNNNN at end
    if 'dotproperty' in url_lower:
        return bool(re.search(r'_\d{5,}$|/\d{5,}$', url_lower))
    # fazwaz: listings have /property-sales/ or u followed by digits
    if 'fazwaz' in url_lower:
        return bool(re.search(r'/property-sales/|u\d{5,}', url_lower))
    # vietnam-real.estate: listings have /property/ with slug
    if 'vietnam-real.estate' in url_lower:
        path = re.sub(r'https?://[^/]+', '', url_lower).strip('/')
        segments = [s for s in path.split('/') if s]
        return len(segments) >= 3
    # tranio: listings have /vietnam/ with specific property
    if 'tranio.com' in url_lower:
        return bool(re.search(r'/\d{5,}', url_lower))
    # asia.villas: individual listings
    if 'asia.villas' in url_lower:
        return bool(re.search(r'/\d{5,}|/property/', url_lower))
    # Generic: must have numeric ID and decent path depth
    path = re.sub(r'https?://[^/]+', '', url_lower).strip('/')
    segments = [s for s in path.split('/') if s]
    return len(segments) >= 2 and bool(re.search(r'\d{5,}', url_lower))


def _find_listing_url_in_block(block, listing_links, base_url):
    """Find the most relevant individual listing URL for a markdown block."""
    # Look for markdown links in the block: [text](url)
    md_links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', block)
    for _text, url in md_links:
        url_full = url if url.startswith('http') else base_url.rstrip('/') + '/' + url.lstrip('/')
        if url_full in listing_links or _is_individual_listing_url(url_full.lower(), ''):
            return url_full

    # Look for bare URLs in the block
    bare_urls = re.findall(r'https?://[^\s\)]+', block)
    for url in bare_urls:
        if url in listing_links or _is_individual_listing_url(url.lower(), ''):
            return url

    # Try to match block content to a listing link by keyword overlap
    block_lower = block.lower()
    best_url = None
    best_score = 0
    for url in listing_links:
        path_words = re.findall(r'[a-z]{3,}', url.lower().split('/')[-1])
        score = sum(1 for w in path_words if w in block_lower)
        if score > best_score:
            best_score = score
            best_url = url
    if best_score >= 2:
        return best_url

    return None


def _extract_title_from_block(block):
    """Extract a title from a markdown block."""
    # Try markdown heading
    heading = re.search(r'^#{1,3}\s+(.+)$', block, re.MULTILINE)
    if heading:
        title = heading.group(1).strip()
        title = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', title)
        if len(title) > 5:
            return title[:200]

    # Try first bold text
    bold = re.search(r'\*\*([^*]+)\*\*', block)
    if bold and len(bold.group(1).strip()) > 5:
        return bold.group(1).strip()[:200]

    # Try first markdown link text
    link = re.search(r'\[([^\]]{5,})\]', block)
    if link:
        text = link.group(1).strip()
        # Skip image alt text
        if not text.startswith('Ảnh') and not text.startswith('!'):
            return text[:200]

    # First non-empty line that's not an image
    for line in block.split('\n'):
        line = line.strip().lstrip('#').strip()
        if len(line) > 10 and not line.startswith('![') and not line.startswith('|'):
            return line[:200]

    return None


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def translate_to_russian(text):
    """Translate Vietnamese/English text to Russian using Google Translate."""
    if not text or len(text.strip()) < 3:
        return text
    try:
        encoded = urllib.parse.quote(text[:500])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ru&dt=t&q={encoded}"
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            translated = ''.join(part[0] for part in data[0] if part[0])
            return translated
    except Exception as e:
        print(f"  Translation error: {e}")
        return text


def is_mostly_ascii(text):
    if not text:
        return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.85


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def extract_price(text, vnd_per_eur=27000):
    """Extract price in EUR from text."""
    text_lower = text.lower()

    # Direct USD patterns -> convert to EUR (1 USD ~ 0.92 EUR)
    usd_patterns = [
        (r'\$\s*([\d,\.]+)\s*k\b', True),
        (r'\$\s*([\d,\.]+)\s*(?:usd)?', False),
        (r'([\d,\.]+)\s*(?:usd|us\$)', False),
    ]
    for pat, is_k in usd_patterns:
        m = re.search(pat, text_lower)
        if m:
            val = _clean_number(m.group(1))
            if is_k or 'k' in text_lower[m.start():m.end()+2]:
                val *= 1000
            if val < 500:
                val *= 1000
            if 10000 <= val <= 10_000_000:
                return round(val * 0.92)

    # EUR patterns
    eur_match = re.search(r'[€]\s*([\d,\.]+)\s*(k|thousand|million)?', text_lower)
    if eur_match:
        val = _clean_number(eur_match.group(1))
        suffix = eur_match.group(2) or ''
        if suffix in ('k', 'thousand'):
            val *= 1000
        elif suffix == 'million':
            val *= 1_000_000
        if val > 1000:
            return round(val)

    # VND billions (tỷ) -> EUR
    vnd_bil = re.search(r'([\d,\.]+)\s*(?:tỷ|ty|billion|bil)\b', text_lower)
    if vnd_bil:
        val = _clean_number(vnd_bil.group(1))
        eur = val * 1_000_000_000 / vnd_per_eur
        if eur > 500:
            return round(eur)

    # VND millions (triệu) -> EUR
    vnd_mil = re.search(r'([\d,\.]+)\s*(?:triệu|trieu|million vnd|tr)\b', text_lower)
    if vnd_mil:
        val = _clean_number(vnd_mil.group(1))
        eur = val * 1_000_000 / vnd_per_eur
        if eur > 500:
            return round(eur)

    # VND with đ or VND suffix
    vnd_direct = re.search(r'vnd\s*([\d,\.]+)', text_lower)
    if not vnd_direct:
        vnd_direct = re.search(r'([\d,\.]+)\s*(?:vnd|đ)', text_lower)
    if vnd_direct:
        val = _clean_number(vnd_direct.group(1))
        if val > 1_000_000_000:
            eur = val / vnd_per_eur
            if eur > 500:
                return round(eur)

    return None


def extract_raw_price(text):
    patterns = [
        r'\$[\d,\.]+\s*(?:k|m|usd|million|thousand)?',
        r'[\d,\.]+\s*(?:tỷ|ty|billion|triệu|trieu|million)\s*(?:vnd|đ|dong)?',
        r'[\d,\.]+\s*(?:usd|us\$)',
        r'[€][\d,\.]+',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_size(text):
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:sqm|m²|m2|sq\.?\s*m)',
        r'(\d+(?:\.\d+)?)\s*(?:square\s*meter)',
        r'(\d+(?:\.\d+)?)\s*SqM',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 10 <= val <= 1000:
                return val
    return None


def extract_bedrooms(text):
    text_lower = text.lower()
    if 'studio' in text_lower:
        return 0
    patterns = [
        r'(\d+)\s*(?:br|bed|bedroom|phòng ngủ|pn)',
        r'(\d+)\s*(?:-?\s*bed)',
        r'(\d+)\s*Bed',
    ]
    for pat in patterns:
        m = re.search(pat, text if 'Bed' in pat else text_lower)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 10:
                return val
    return None


def extract_developer(text, known_developers):
    text_lower = text.lower()
    for dev_name in known_developers:
        if dev_name in text_lower:
            return dev_name.title()
    return None


def extract_bathrooms(text):
    text_lower = text.lower()
    patterns = [
        r'(\d+)\s*(?:bathroom|bath|wc|vệ sinh|phòng tắm)',
        r'(\d+)\s*(?:-?\s*bath)',
    ]
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 10:
                return val
    return None


def extract_legal_status(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ['sổ hồng', 'freehold', 'long-term', 'lâu dài', 'permanent']):
        return 'Собственность'
    if any(w in text_lower for w in ['hợp đồng mua bán', 'sale contract', 'purchase contract']):
        return 'Договор купли-продажи'
    if any(w in text_lower for w in ['leasehold', '50 year', '50-year', '50 năm']):
        return 'Аренда 50 лет'
    if any(w in text_lower for w in ['sở hữu', 'foreign quota', 'foreign ownership']):
        return 'Иностр. квота'
    return None


def extract_furnishing(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ['full furniture', 'fully furnished', 'nội thất đầy đủ', 'full nội thất']):
        return 'Полная меблировка'
    if any(w in text_lower for w in ['basic', 'cơ bản', 'basic furniture', 'nội thất cơ bản']):
        return 'Базовая'
    if any(w in text_lower for w in ['unfurnished', 'bare', 'không nội thất']):
        return 'Без мебели'
    if any(w in text_lower for w in ['furnished', 'nội thất']):
        return 'Меблировано'
    return None


def generate_listing_id(listing):
    key = f"{listing.get('title_original', listing.get('title', ''))}|{listing.get('url', '')}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Main search round — Firecrawl edition
# ---------------------------------------------------------------------------

def run_search_round(config):
    """
    Run one complete search round by scraping portal listing pages
    directly with Firecrawl.
    """
    firecrawl_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not firecrawl_key:
        print("ERROR: FIRECRAWL_API_KEY not set!")
        return []

    all_listings = []
    scrape_targets = config.get("scrape_targets", [])

    if not scrape_targets:
        print("ERROR: No scrape_targets configured!")
        return []

    credits_used = 0

    for target in scrape_targets:
        loc_key = target["location_key"]
        portal_name = target["portal"]
        page_url = target["url"]
        base_url = target.get("base_url", re.match(r'https?://[^/]+', page_url).group(0))
        loc_config = config['locations'].get(loc_key, {})

        print(f"\n{'='*50}")
        print(f"  Scraping: {portal_name} → {loc_config.get('label_en', loc_key)}")
        print(f"  URL: {page_url}")
        print(f"{'='*50}")

        try:
            page_data = firecrawl_scrape(page_url, firecrawl_key)
            credits_used += 1

            if not page_data:
                print(f"  No data returned")
                continue

            md_len = len(page_data.get("markdown", ""))
            n_links = len(page_data.get("links", []))
            print(f"  Got {md_len} chars markdown, {n_links} links")

            listings = parse_listings_from_page(
                page_data, portal_name, loc_key, base_url, config
            )
            print(f"  Extracted {len(listings)} apartment listings")

            for lst in listings:
                br = lst.get('bedrooms')
                br_str = f"{br}BR" if br is not None else "?BR"
                sz = lst.get('size_sqm')
                sz_str = f"{sz}m²" if sz else "?m²"
                print(f"    ✓ €{lst['price_eur']:,} | {br_str} | {sz_str} | {lst['title_original'][:50]}")

            all_listings.extend(listings)
            time.sleep(1)

        except Exception as e:
            print(f"  WARNING: Failed to scrape {portal_name}/{loc_key}: {e}")
            continue

    print(f"\n  Total Firecrawl credits used this run: {credits_used}")
    return all_listings


# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------

def load_seen_listings(data_dir="data"):
    seen_file = Path(data_dir) / "seen_listings.json"
    if seen_file.exists():
        with open(seen_file, encoding='utf-8-sig') as f:
            return json.load(f)
    return {}


def save_seen_listings(seen, data_dir="data"):
    Path(data_dir).mkdir(exist_ok=True)
    seen_file = Path(data_dir) / "seen_listings.json"
    with open(seen_file, 'w', encoding='utf-8') as f:
        json.dump(seen, f, indent=2)


def load_published_listings(data_dir="data"):
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, encoding='utf-8-sig') as f:
            return json.load(f)
    return {"rounds": []}


def save_published_listings(published, data_dir="data"):
    Path(data_dir).mkdir(exist_ok=True)
    pub_file = Path(data_dir) / "published_listings.json"
    with open(pub_file, 'w', encoding='utf-8') as f:
        json.dump(published, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    config = load_config()
    print("Running test scrape...")
    listings = run_search_round(config)
    print(f"\nTotal listings found: {len(listings)}")
    for l in listings[:5]:
        print(f"  - {l['title'][:60]} | {l['portal']} | €{l.get('price_eur', 'N/A')}")
