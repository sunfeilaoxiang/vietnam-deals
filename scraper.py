"""
Vietnam Property Scraper — Firecrawl Two-Pass Edition
Pass 1: Scrape search/listing pages to collect individual listing URLs.
Pass 2: Scrape each individual listing page to get accurate property data.
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

LAND_SKIP_TERMS = [
    'bán đất', 'ban dat', 'đất nền', 'dat nen', 'đất thổ', 'dat tho',
    'land for sale', 'đất đẹp', 'lô đất', 'lo dat',
    'biệt thự', 'biet thu', 'villa for sale',
    'nhà riêng', 'nha rieng', 'nhà phố', 'nha pho',
    'shophouse', 'shop house', 'townhouse', 'town house',
    'liền kề', 'lien ke', 'song lập', 'song lap',
    'warehouse', 'kho xưởng', 'factory',
]


def _is_apartment_page(text):
    """Check if a page is about an apartment/condo, not land or villa."""
    text_lower = text.lower()
    for term in LAND_SKIP_TERMS:
        if term in text_lower:
            if any(apt in text_lower for apt in ['căn hộ', 'can ho', 'apartment', 'condo', 'chung cư', 'chung cu']):
                continue
            return False
    return True


# ---------------------------------------------------------------------------
# Pass 1: Extract individual listing URLs from search pages
# ---------------------------------------------------------------------------

def _is_individual_listing_url(url_lower, portal_name=''):
    """Check if a URL looks like an individual property listing page."""
    # batdongsan: individual listings have prXXXXX or end in .html with a slug
    if 'batdongsan.com.vn' in url_lower:
        return bool(re.search(r'pr\d{5,}', url_lower))
    # dotproperty: listings have _NNNNNNN at end
    if 'dotproperty' in url_lower:
        return bool(re.search(r'_\d{5,}$|/\d{5,}$', url_lower))
    # fazwaz: listings have /property-sales/ or u followed by digits
    if 'fazwaz' in url_lower:
        return bool(re.search(r'/property-sales/|u\d{5,}', url_lower))
    # vietnam-real.estate: listings have /property/ with deep slug
    if 'vietnam-real.estate' in url_lower:
        path = re.sub(r'https?://[^/]+', '', url_lower).strip('/')
        segments = [s for s in path.split('/') if s]
        return len(segments) >= 3
    # tranio: listings have /vietnam/ with numeric ID
    if 'tranio.com' in url_lower:
        return bool(re.search(r'/\d{5,}', url_lower))
    # nhatot: individual listings have numeric ID path
    if 'nhatot.com' in url_lower:
        return bool(re.search(r'/\d{8,}\.htm', url_lower))
    # Generic: must have numeric ID and decent path depth
    path = re.sub(r'https?://[^/]+', '', url_lower).strip('/')
    segments = [s for s in path.split('/') if s]
    return len(segments) >= 2 and bool(re.search(r'\d{5,}', url_lower))


def extract_listing_urls_from_search(page_data, portal_name, base_url):
    """
    Pass 1: Extract all individual listing URLs from a search results page.
    Returns a list of absolute URLs.
    """
    links = page_data.get("links", [])
    markdown = page_data.get("markdown", "")
    found_urls = set()

    # From the links array
    for link in links:
        url = link if isinstance(link, str) else link.get("url", link.get("href", ""))
        if not url:
            continue
        url_lower = url.lower()
        # Skip obviously non-listing URLs
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
            found_urls.add(url)

    # Also extract URLs from markdown links: [text](url)
    md_links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', markdown)
    for _text, url in md_links:
        url_full = url if url.startswith('http') else base_url.rstrip('/') + '/' + url.lstrip('/')
        if _is_individual_listing_url(url_full.lower(), portal_name):
            found_urls.add(url_full)

    return list(found_urls)


# ---------------------------------------------------------------------------
# Portal-specific structured parsers
# ---------------------------------------------------------------------------

def _parse_batdongsan_structured(markdown, vnd_per_eur):
    """
    Parse the 'Đặc điểm bất động sản' structured section from batdongsan pages.
    Returns a dict of extracted fields, or empty dict if section not found.
    """
    result = {}

    # Find the structured property details section
    section_start = markdown.find('Đặc điểm bất động sản')
    if section_start < 0:
        # Try the summary bar that appears earlier
        section_start = markdown.find('Khoảng giá')
        if section_start < 0:
            return result

    # Take a generous chunk from the section
    section = markdown[section_start:section_start + 800]

    # Price: "Khoảng giáX,X tỷ" or "Khoảng giáXXX triệu"
    # Vietnamese uses comma as decimal separator: "2,7 tỷ" = 2.7 billion VND
    # IMPORTANT: Prefer tỷ over triệu — triệu in Khoảng giá is often price/m²
    price_match_ty = re.search(r'Khoảng giá\s*([\d,\.]+)\s*tỷ', section)
    price_match_trieu = re.search(r'Khoảng giá\s*([\d,\.]+)\s*triệu', section)
    price_match = price_match_ty or price_match_trieu
    if price_match:
        raw_num = price_match.group(1)
        # Handle Vietnamese decimal: "2,7" -> 2.7, "10,5" -> 10.5
        # But also "1.500" -> 1500 (dot as thousand separator)
        if ',' in raw_num and raw_num.count(',') == 1:
            # Single comma: treat as decimal separator (Vietnamese style)
            val = float(raw_num.replace(',', '.'))
        else:
            val = _clean_number(raw_num)
        if price_match_ty:
            result['price_eur'] = round(val * 1_000_000_000 / vnd_per_eur)
            result['price_raw'] = f"{raw_num} tỷ"
        else:
            # triệu: only accept if value is realistic for total price (>= 500 triệu = ~€18.5k)
            eur_val = round(val * 1_000_000 / vnd_per_eur)
            if eur_val >= 18000:
                result['price_eur'] = eur_val
                result['price_raw'] = f"{raw_num} triệu"
            # else: skip — likely price/m² or deposit, let generic parser try

    # Area: "Diện tíchXX m²"
    area_match = re.search(r'Diện tích\s*([\d,\.]+)\s*m²', section)
    if area_match:
        val = float(area_match.group(1))
        if 10 <= val <= 1000:
            result['size_sqm'] = val

    # Bedrooms: "Số phòng ngủX phòng" or "Phòng ngủX PN"
    br_match = re.search(r'(?:Số phòng ngủ|Phòng ngủ)\s*(\d+)', section)
    if br_match:
        result['bedrooms'] = int(br_match.group(1))

    # Bathrooms: "Số phòng tắm, vệ sinhX phòng"
    bath_match = re.search(r'(?:Số phòng tắm|phòng tắm|vệ sinh)\s*(\d+)', section)
    if bath_match:
        result['bathrooms'] = int(bath_match.group(1))

    # Legal status: "Pháp lýXXX"
    legal_match = re.search(r'Pháp lý\s*(.+?)(?:\n|$|Nội thất|Thông tin)', section)
    if legal_match:
        legal_text = legal_match.group(1).strip()
        if 'sổ hồng' in legal_text.lower() or 'sổ đỏ' in legal_text.lower():
            result['legal_status'] = 'Собственность'
        elif 'hợp đồng' in legal_text.lower():
            result['legal_status'] = 'Договор купли-продажи'

    # Furnishing: "Nội thấtXXX"
    furn_match = re.search(r'Nội thất\s*(.+?)(?:\n|$|Thông tin|Đặc điểm)', section)
    if furn_match:
        furn_text = furn_match.group(1).strip().lower()
        if 'full' in furn_text or 'đầy đủ' in furn_text:
            result['furnishing'] = 'Полная меблировка'
        elif 'cơ bản' in furn_text or 'basic' in furn_text:
            result['furnishing'] = 'Базовая'
        elif 'không' in furn_text:
            result['furnishing'] = 'Без мебели'
        elif furn_text:
            result['furnishing'] = 'Меблировано'

    # Direction: "Hướng nhàXXX"
    dir_match = re.search(r'Hướng nhà\s*(.+?)(?:\n|$|Hướng ban)', section)
    if dir_match:
        result['direction'] = dir_match.group(1).strip()

    return result


def _parse_dotproperty_structured(markdown, vnd_per_eur):
    """Parse structured data from dotproperty listing pages."""
    result = {}

    # dotproperty usually has "฿X,XXX,XXX" or "$XXX,XXX" prices
    # and "X Bedrooms · X Bathrooms · XX sqm" format
    beds_match = re.search(r'(\d+)\s*(?:Bedroom|Bed)', markdown)
    if beds_match:
        result['bedrooms'] = int(beds_match.group(1))

    baths_match = re.search(r'(\d+)\s*(?:Bathroom|Bath)', markdown)
    if baths_match:
        result['bathrooms'] = int(baths_match.group(1))

    sqm_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:sqm|m²|SqM)', markdown)
    if sqm_match:
        val = float(sqm_match.group(1))
        if 10 <= val <= 1000:
            result['size_sqm'] = val

    return result


def _parse_fazwaz_structured(markdown, vnd_per_eur):
    """Parse structured data from fazwaz listing pages."""
    result = {}

    # fazwaz has structured sections like "X Beds · X Baths · XX SqM"
    beds_match = re.search(r'(\d+)\s*Bed', markdown)
    if beds_match:
        result['bedrooms'] = int(beds_match.group(1))

    baths_match = re.search(r'(\d+)\s*Bath', markdown)
    if baths_match:
        result['bathrooms'] = int(baths_match.group(1))

    sqm_match = re.search(r'(\d+(?:\.\d+)?)\s*SqM', markdown)
    if sqm_match:
        val = float(sqm_match.group(1))
        if 10 <= val <= 1000:
            result['size_sqm'] = val

    return result


# ---------------------------------------------------------------------------
# Pass 2: Parse a single listing page for property details
# ---------------------------------------------------------------------------

def parse_single_listing(page_data, listing_url, portal_name, location_key, config):
    """
    Pass 2: Extract property details from an individual listing page.
    Uses portal-specific structured parsers for accurate data extraction,
    falling back to generic regex extraction for non-supported portals.
    Returns a listing dict or None if the page doesn't look like a valid apartment listing.
    """
    markdown = page_data.get("markdown", "")
    if not markdown or len(markdown.strip()) < 50:
        return None

    vnd_per_eur = config.get("vnd_per_eur", 27000)
    budget_max = config.get("budget_max_eur", 150000)

    # Check if this is actually an apartment listing
    if not _is_apartment_page(markdown):
        return None

    # Extract title from metadata first (most reliable), then from page content
    title = _extract_page_title(markdown, page_data)
    if not title or len(title) < 5:
        return None

    # --- Portal-specific structured extraction ---
    structured = {}
    url_lower = listing_url.lower()
    if 'batdongsan.com.vn' in url_lower:
        structured = _parse_batdongsan_structured(markdown, vnd_per_eur)
    elif 'dotproperty' in url_lower:
        structured = _parse_dotproperty_structured(markdown, vnd_per_eur)
    elif 'fazwaz' in url_lower:
        structured = _parse_fazwaz_structured(markdown, vnd_per_eur)

    # Use structured data with fallback to generic regex extraction
    price_eur = structured.get('price_eur') or extract_price(markdown, vnd_per_eur)
    if not price_eur:
        return None

    # Skip if way over budget (>3x) — likely bad parse
    if price_eur > budget_max * 3:
        return None

    # Minimum price floor: no real apartment sells for < €20,000
    # Values below this are typically price/m², deposits, or monthly installments
    if price_eur < 20000:
        return None

    size_sqm = structured.get('size_sqm') or extract_size(markdown)
    bedrooms = structured.get('bedrooms') if 'bedrooms' in structured else extract_bedrooms(markdown)
    bathrooms = structured.get('bathrooms') if 'bathrooms' in structured else extract_bathrooms(markdown)
    legal_status = structured.get('legal_status') or extract_legal_status(markdown)
    furnishing = structured.get('furnishing') or extract_furnishing(markdown)
    developer = extract_developer(markdown, config.get('known_developers', {}))
    price_raw = structured.get('price_raw') or extract_raw_price(markdown)

    # Translate title to Russian
    title_ru = translate_to_russian(title) if not is_mostly_ascii(title) else title
    desc_snippet = _extract_description(markdown)
    desc_ru = translate_to_russian(desc_snippet) if not is_mostly_ascii(desc_snippet) else desc_snippet

    listing = {
        'title': title_ru,
        'title_original': title,
        'url': listing_url,
        'portal': portal_name,
        'location_key': location_key,
        'price_eur': price_eur,
        'price_raw': price_raw,
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
    return listing


def _extract_page_title(markdown, page_data=None):
    """Extract the main title from a single listing page."""
    # Try metadata title first (Firecrawl sometimes returns it)
    if page_data:
        meta = page_data.get("metadata", {})
        title = meta.get("title", "")
        if title and len(title) > 5:
            # Clean up common suffixes
            title = re.sub(r'\s*[-|·]\s*(Batdongsan|BatDongSan|dotproperty|FazWaz|Nhà Tốt|nhatot).*$', '', title, flags=re.IGNORECASE)
            if len(title) > 5:
                return title.strip()[:200]

    # Try first H1 heading
    h1 = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()
        title = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', title)
        if len(title) > 5:
            return title[:200]

    # Try first H2 heading
    h2 = re.search(r'^##\s+(.+)$', markdown, re.MULTILINE)
    if h2:
        title = h2.group(1).strip()
        title = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', title)
        if len(title) > 5:
            return title[:200]

    # Try first bold text
    bold = re.search(r'\*\*([^*]{5,})\*\*', markdown)
    if bold:
        return bold.group(1).strip()[:200]

    # First substantial line
    for line in markdown.split('\n'):
        line = line.strip().lstrip('#').strip()
        if len(line) > 10 and not line.startswith('![') and not line.startswith('|'):
            return line[:200]

    return None


def _extract_description(markdown):
    """Extract a clean description snippet from the listing page."""
    lines = markdown.split('\n')
    desc_parts = []
    for line in lines:
        line = line.strip()
        # Skip images, headers, links-only lines, very short lines
        if not line or line.startswith('![') or line.startswith('#') or len(line) < 20:
            continue
        # Skip navigation/menu-like lines
        if line.count('[') > 3:
            continue
        # Clean markdown formatting
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
        clean = clean.strip()
        if len(clean) > 20:
            desc_parts.append(clean)
            if len(' '.join(desc_parts)) > 300:
                break
    return ' '.join(desc_parts)[:500] if desc_parts else ''


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
# Field extractors (used on individual listing pages — more reliable)
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
    # Vietnamese uses comma as decimal: "2,7 tỷ" = 2.7 billion
    vnd_bil = re.search(r'([\d,\.]+)\s*(?:tỷ|ty|billion|bil)\b', text_lower)
    if vnd_bil:
        raw_num = vnd_bil.group(1)
        if ',' in raw_num and raw_num.count(',') == 1 and len(raw_num.split(',')[1]) <= 2:
            val = float(raw_num.replace(',', '.'))
        else:
            val = _clean_number(raw_num)
        eur = val * 1_000_000_000 / vnd_per_eur
        if eur > 500:
            return round(eur)

    # VND millions (triệu) -> EUR
    # Careful: many pages show "triệu/m²" (price per sqm), not total price
    # Only accept if result is >= €18,000 (= 500 triệu), which is a realistic min apartment price
    vnd_mil = re.search(r'([\d,\.]+)\s*(?:triệu|trieu|million vnd|tr)\b', text_lower)
    if vnd_mil:
        raw_num = vnd_mil.group(1)
        if ',' in raw_num and raw_num.count(',') == 1 and len(raw_num.split(',')[1]) <= 2:
            val = float(raw_num.replace(',', '.'))
        else:
            val = _clean_number(raw_num)
        eur = val * 1_000_000 / vnd_per_eur
        if eur >= 18000:
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
    key = f"{listing.get('url', '')}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Main two-pass search round
# ---------------------------------------------------------------------------

def run_search_round(config):
    """
    Run one complete search round using the two-pass approach:
    Pass 1: Scrape search pages → collect individual listing URLs
    Pass 2: Scrape each listing page → extract accurate property data
    """
    firecrawl_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not firecrawl_key:
        print("ERROR: FIRECRAWL_API_KEY not set!")
        return []

    scrape_targets = config.get("scrape_targets", [])
    if not scrape_targets:
        print("ERROR: No scrape_targets configured!")
        return []

    credits_used = 0
    budget_max = config.get("budget_max_eur", 150000)

    # ---------------------------------------------------------------
    # Pass 1: Collect listing URLs from search pages
    # ---------------------------------------------------------------
    print("\n  === PASS 1: Collecting listing URLs from search pages ===")
    listing_urls_by_loc = {}  # {(url, loc_key, portal_name, base_url)}

    for target in scrape_targets:
        loc_key = target["location_key"]
        portal_name = target["portal"]
        page_url = target["url"]
        base_url = target.get("base_url", re.match(r'https?://[^/]+', page_url).group(0))
        loc_config = config['locations'].get(loc_key, {})

        print(f"\n  Scraping: {portal_name} → {loc_config.get('label_en', loc_key)}")
        print(f"  URL: {page_url}")

        try:
            page_data = firecrawl_scrape(page_url, firecrawl_key)
            credits_used += 1

            if not page_data:
                print(f"    No data returned")
                continue

            urls = extract_listing_urls_from_search(page_data, portal_name, base_url)
            print(f"    Found {len(urls)} listing URLs")

            for url in urls:
                listing_urls_by_loc.setdefault(loc_key, []).append({
                    'url': url,
                    'portal': portal_name,
                    'base_url': base_url,
                })

            time.sleep(0.5)

        except Exception as e:
            print(f"    WARNING: Failed to scrape search page {portal_name}/{loc_key}: {e}")
            continue

    # Deduplicate URLs across portals (same listing may appear on multiple search pages)
    all_url_entries = []
    seen_urls = set()
    for loc_key, entries in listing_urls_by_loc.items():
        for entry in entries:
            url_normalized = entry['url'].rstrip('/').lower()
            if url_normalized not in seen_urls:
                seen_urls.add(url_normalized)
                all_url_entries.append({**entry, 'location_key': loc_key})

    total_urls = len(all_url_entries)
    print(f"\n  Pass 1 complete: {total_urls} unique listing URLs found")
    print(f"  Credits used (search pages): {credits_used}")

    # Credit budget check: cap individual scrapes to stay within reason
    # Reserve ~30 credits for search pages, use the rest for individual listings
    max_listing_scrapes = min(total_urls, 120)  # cap at 120 per run
    if total_urls > max_listing_scrapes:
        print(f"  Capping to {max_listing_scrapes} listing scrapes (of {total_urls} found)")
        # Prioritize: spread evenly across locations
        by_loc = {}
        for entry in all_url_entries:
            by_loc.setdefault(entry['location_key'], []).append(entry)
        per_loc = max(5, max_listing_scrapes // len(by_loc))
        capped = []
        for loc_key, entries in by_loc.items():
            capped.extend(entries[:per_loc])
        all_url_entries = capped[:max_listing_scrapes]

    # ---------------------------------------------------------------
    # Pass 2: Scrape individual listing pages
    # ---------------------------------------------------------------
    print(f"\n  === PASS 2: Scraping {len(all_url_entries)} individual listing pages ===")
    all_listings = []

    for i, entry in enumerate(all_url_entries):
        url = entry['url']
        loc_key = entry['location_key']
        portal = entry['portal']

        if (i + 1) % 10 == 0 or i == 0:
            print(f"\n  [{i+1}/{len(all_url_entries)}] Scraping listings...")

        try:
            page_data = firecrawl_scrape(url, firecrawl_key)
            credits_used += 1

            if not page_data:
                continue

            listing = parse_single_listing(
                page_data, url, portal, loc_key, config
            )

            if listing:
                br = listing.get('bedrooms')
                br_str = f"{br}BR" if br is not None else "?BR"
                sz = listing.get('size_sqm')
                sz_str = f"{sz}m²" if sz else "?m²"
                print(f"    ✓ €{listing['price_eur']:,} | {br_str} | {sz_str} | {listing['title_original'][:50]}")
                all_listings.append(listing)
            else:
                print(f"    ✗ Skipped: {url[:80]}")

            # Rate limiting: small delay between requests
            time.sleep(0.5)

        except Exception as e:
            print(f"    WARNING: Failed to scrape listing {url[:60]}: {e}")
            continue

    print(f"\n  Pass 2 complete: {len(all_listings)} valid listings extracted")
    print(f"  Total Firecrawl credits used this run: {credits_used}")
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
