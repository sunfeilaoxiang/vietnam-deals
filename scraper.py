"""
Vietnam Property Scraper
Searches property portals via web search APIs, extracts listing data,
and returns structured results for scoring.
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


def _clean_number(s):
    """Clean a number string that may use dots or commas as thousand separators."""
    s = s.strip()
    # Remove any non-numeric chars except dots, commas, minus
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
from datetime import datetime
from pathlib import Path


def load_config(config_path="config.json"):
    with open(config_path, encoding='utf-8-sig') as f:
        return json.load(f)


def web_search(query, num_results=10):
    """
    Search the web using SerpAPI (free tier: 100 searches/month)
    or fallback to DuckDuckGo HTML scraping.
    """
    serpapi_key = os.environ.get('SERPAPI_KEY', '')
    if serpapi_key:
        return _search_serpapi(query, serpapi_key, num_results)
    else:
        return _search_duckduckgo(query, num_results)


def _search_serpapi(query, api_key, num_results):
    """Search via SerpAPI (Google results)."""
    params = urllib.parse.urlencode({
        'q': query,
        'api_key': api_key,
        'engine': 'google',
        'num': num_results,
        'gl': 'vn',
        'hl': 'en'
    })
    url = f"https://serpapi.com/search.json?{params}"
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'VietnamPropertyBot/1.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            results = []
            for r in data.get('organic_results', [])[:num_results]:
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('link', ''),
                    'snippet': r.get('snippet', '')
                })
            return results
    except Exception as e:
        print(f"  SerpAPI error: {e}")
        return []


def _search_duckduckgo(query, num_results):
    """Search via DuckDuckGo Lite (no API key needed)."""
    params = urllib.parse.urlencode({'q': query, 'kl': 'vn-en'})
    url = f"https://lite.duckduckgo.com/lite/?{params}"
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            results = []
            link_pattern = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="result-link"[^>]*>([^<]+)</a>', html)
            snippet_pattern = re.findall(r'<td class="result-snippet">([^<]+)</td>', html)
            if not link_pattern:
                link_pattern = re.findall(r'<a[^>]+rel="nofollow"[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html)
            for i, (url_match, title) in enumerate(link_pattern[:num_results]):
                snippet = snippet_pattern[i] if i < len(snippet_pattern) else ''
                results.append({
                    'title': title.strip(),
                    'url': url_match.strip(),
                    'snippet': snippet.strip()
                })
            return results
    except Exception as e:
        print(f"  DuckDuckGo error: {e}")
        return []


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


def extract_listing_from_search_result(result, portal_name, location_key, config):
    """Extract structured listing data from a search result."""
    title = result.get('title', '')
    snippet = result.get('snippet', '')
    url = result.get('url', '')
    combined = f"{title} {snippet}"

    vnd_per_eur = config.get('vnd_per_eur', 27000)

    price_eur = extract_price(combined, vnd_per_eur)
    size_sqm = extract_size(combined)
    bedrooms = extract_bedrooms(combined)
    bathrooms = extract_bathrooms(combined)
    developer = extract_developer(combined, config.get('known_developers', {}))
    legal_status = extract_legal_status(combined)
    furnishing = extract_furnishing(combined)

    # Translate title and snippet to Russian
    title_ru = translate_to_russian(title) if not is_mostly_ascii(title) else title
    snippet_ru = translate_to_russian(snippet) if not is_mostly_ascii(snippet) else snippet

    listing = {
        'title': title_ru,
        'title_original': title,
        'url': url,
        'portal': portal_name,
        'location_key': location_key,
        'price_eur': price_eur,
        'price_raw': extract_raw_price(combined),
        'size_sqm': size_sqm,
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'developer': developer,
        'legal_status': legal_status,
        'furnishing': furnishing,
        'description': snippet_ru,
        'description_original': snippet,
        'sea_proximity': None,
        'found_date': datetime.now().strftime('%Y-%m-%d'),
        'source_snippet': snippet_ru[:300]
    }
    return listing


def is_mostly_ascii(text):
    """Check if text is mostly ASCII (English)."""
    if not text:
        return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.85


def extract_price(text, vnd_per_eur=27000):
    """Extract price in EUR from text."""
    text_lower = text.lower()

    # Direct USD patterns -> convert to EUR (1 USD ~ 0.92 EUR)
    usd_patterns = [
        (r'\$\s*([\d,\.]+)\s*k\b', True),        # $85k
        (r'\$\s*([\d,\.]+)\s*(?:usd)?', False),   # $85,000
        (r'([\d,\.]+)\s*(?:usd|us\$)', False),    # 85000 USD
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
                return round(val * 0.92)  # USD to EUR

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
    vnd_bil = re.search(r'([\d,\.]+)\s*(?:t\u1ef7|ty|billion|bil)\b', text_lower)
    if vnd_bil:
        val = _clean_number(vnd_bil.group(1))
        eur = val * 1_000_000_000 / vnd_per_eur
        if eur > 500:
            return round(eur)

    # VND millions (triệu) -> EUR
    vnd_mil = re.search(r'([\d,\.]+)\s*(?:tri\u1ec7u|trieu|million vnd|tr)\b', text_lower)
    if vnd_mil:
        val = _clean_number(vnd_mil.group(1))
        eur = val * 1_000_000 / vnd_per_eur
        if eur > 500:
            return round(eur)

    # VND with đ or VND suffix
    vnd_direct = re.search(r'vnd\s*([\d,\.]+)', text_lower)
    if not vnd_direct:
        vnd_direct = re.search(r'([\d,\.]+)\s*(?:vnd|\u0111)', text_lower)
    if vnd_direct:
        val = _clean_number(vnd_direct.group(1))
        if val > 1_000_000_000:
            eur = val / vnd_per_eur
            if eur > 500:
                return round(eur)

    return None


def extract_raw_price(text):
    """Extract raw price string for display."""
    patterns = [
        r'\$[\d,\.]+\s*(?:k|m|usd|million|thousand)?',
        r'[\d,\.]+\s*(?:t\u1ef7|ty|billion|tri\u1ec7u|trieu|million)\s*(?:vnd|\u0111|dong)?',
        r'[\d,\.]+\s*(?:usd|us\$)',
        r'[€][\d,\.]+',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_size(text):
    """Extract square meters from text."""
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:sqm|m\u00b2|m2|sq\.?\s*m)',
        r'(\d+(?:\.\d+)?)\s*(?:square\s*meter)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 10 <= val <= 1000:
                return val
    return None


def extract_bedrooms(text):
    """Extract bedroom count from text."""
    text_lower = text.lower()
    if 'studio' in text_lower:
        return 0
    patterns = [
        r'(\d+)\s*(?:br|bed|bedroom|ph\u00f2ng ng\u1ee7|pn)',
        r'(\d+)\s*(?:-?\s*bed)',
    ]
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 10:
                return val
    return None


def extract_developer(text, known_developers):
    """Try to find a known developer in the text."""
    text_lower = text.lower()
    for dev_name in known_developers:
        if dev_name in text_lower:
            return dev_name.title()
    return None


def extract_bathrooms(text):
    """Extract bathroom count from text."""
    text_lower = text.lower()
    patterns = [
        r'(\d+)\s*(?:bathroom|bath|wc|v\u1ec7 sinh|ph\u00f2ng t\u1eafm)',
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
    """Extract legal/ownership status from text."""
    text_lower = text.lower()
    if any(w in text_lower for w in ['s\u1ed5 h\u1ed3ng', 'freehold', 'long-term', 'l\u00e2u d\u00e0i', 'permanent']):
        return '\u0421\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u043e\u0441\u0442\u044c'  # Собственность
    if any(w in text_lower for w in ['h\u1ee3p \u0111\u1ed3ng mua b\u00e1n', 'sale contract', 'purchase contract']):
        return '\u0414\u043e\u0433\u043e\u0432\u043e\u0440 \u043a\u0443\u043f\u043b\u0438-\u043f\u0440\u043e\u0434\u0430\u0436\u0438'  # Договор купли-продажи
    if any(w in text_lower for w in ['leasehold', '50 year', '50-year', '50 n\u0103m']):
        return '\u0410\u0440\u0435\u043d\u0434\u0430 50 \u043b\u0435\u0442'  # Аренда 50 лет
    if any(w in text_lower for w in ['s\u1edf h\u1eefu', 'foreign quota', 'foreign ownership']):
        return '\u0418\u043d\u043e\u0441\u0442\u0440. \u043a\u0432\u043e\u0442\u0430'  # Иностр. квота
    return None


def extract_furnishing(text):
    """Extract furnishing level from text."""
    text_lower = text.lower()
    if any(w in text_lower for w in ['full furniture', 'fully furnished', 'n\u1ed9i th\u1ea5t \u0111\u1ea7y \u0111\u1ee7', 'full n\u1ed9i th\u1ea5t']):
        return '\u041f\u043e\u043b\u043d\u0430\u044f \u043c\u0435\u0431\u043b\u0438\u0440\u043e\u0432\u043a\u0430'  # Полная меблировка
    if any(w in text_lower for w in ['basic', 'c\u01a1 b\u1ea3n', 'basic furniture', 'n\u1ed9i th\u1ea5t c\u01a1 b\u1ea3n']):
        return '\u0411\u0430\u0437\u043e\u0432\u0430\u044f'  # Базовая
    if any(w in text_lower for w in ['unfurnished', 'bare', 'kh\u00f4ng n\u1ed9i th\u1ea5t']):
        return '\u0411\u0435\u0437 \u043c\u0435\u0431\u0435\u043b\u0438'  # Без мебели
    if any(w in text_lower for w in ['furnished', 'n\u1ed9i th\u1ea5t']):
        return '\u041c\u0435\u0431\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u043e'  # Меблировано
    return None


def generate_listing_id(listing):
    """Create a unique hash for deduplication."""
    key = f"{listing.get('title_original', listing.get('title', ''))}|{listing.get('url', '')}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]


def is_relevant_result(result, location_key, config):
    """Filter out irrelevant search results."""
    title = result.get('title', '').lower()
    url = result.get('url', '').lower()
    snippet = result.get('snippet', '').lower()
    combined = f"{title} {snippet}"

    # Must contain property-related terms
    property_terms = ['apartment', 'c\u0103n h\u1ed9', 'condo', 'villa', 'property',
                      'b\u00e1n', 'sale', 'bedroom', 'sqm', 'm\u00b2',
                      'ph\u00f2ng ng\u1ee7', 'resort', 'residence',
                      't\u1ef7', 'tri\u1ec7u', 'price', 'gi\u00e1']
    if not any(term in combined for term in property_terms):
        return False

    # Skip news articles, guides, general pages
    skip_terms = ['news', 'tin t\u1ee9c', 'blog', 'guide', 'how to', 'wikipedia',
                  'youtube', 'apartments-for-rent', 'for-rent', 'cho thu\u00ea']
    if any(term in combined for term in skip_terms):
        return False

    # Skip if title contains generic tag/category indicators
    title_skip = ['- tags', '- b\u00e1n - tags', '- tag', 'danh s\u00e1ch', 'k\u1ebft qu\u1ea3']
    if any(term in title for term in title_skip):
        return False

    # Skip generic directory/category pages
    skip_url_patterns = config.get('skip_url_patterns', [])
    for pattern in skip_url_patterns:
        if pattern in url:
            return False

    return True


def is_specific_listing(listing):
    """
    Check if this is a specific property listing (not a directory page).
    Must have a price to be considered specific.
    """
    # Must have a price
    if not listing.get('price_eur'):
        return False

    # Skip if URL looks like a category/search page
    url = listing.get('url', '').lower()
    generic_patterns = [
        '/search', '/tim-kiem', '/tags/', '/tag/',
        '/tags', 'page=', '/category/', 'apartments-for-sale',
        'property-for-sale', 'condos-for-sale',
        'properties-for-sale', 'bat-dong-san-ban',
        'real-estate-for-sale', '/gia-tu-', '/gia-duoi-',
        '/ban-can-ho-chung-cu-', '/ban-nha-',
    ]
    for pattern in generic_patterns:
        if pattern in url:
            return False

    # Skip if title looks like a category page
    title = listing.get('title_original', listing.get('title', '')).lower()
    if any(t in title for t in ['- tags', '- b\u00e1n - tags', 'danh s\u00e1ch']):
        return False

    return True


def run_search_round(config):
    """Run one complete search round across all locations and portals."""
    all_listings = []
    vnd_per_eur = config.get('vnd_per_eur', 27000)
    budget_vnd = config.get('budget_max_eur', 140000) * vnd_per_eur
    budget_vnd_str = f"{budget_vnd/1e9:.1f} t\u1ef7"

    for loc_key, loc_config in config['locations'].items():
        print(f"\n{'='*50}")
        print(f"Searching: {loc_config.get('label_en', loc_config['label'])}")
        print(f"{'='*50}")

        for portal in config['portals']:
            for keyword in loc_config['search_keywords'][:2]:
                query = portal['search_pattern'].format(
                    keyword=keyword,
                    budget_vnd=budget_vnd_str
                )
                print(f"\n  Portal: {portal['name']} | Query: {query[:80]}...")
                results = web_search(query, num_results=5)
                print(f"  Found {len(results)} results")

                for result in results:
                    if not is_relevant_result(result, loc_key, config):
                        continue
                    listing = extract_listing_from_search_result(
                        result, portal['name'], loc_key, config
                    )
                    # Only keep specific listings with prices
                    if not is_specific_listing(listing):
                        print(f"    Skipped (no price or generic): {listing.get('title_original', '')[:50]}")
                        continue
                    listing['listing_id'] = generate_listing_id(listing)
                    all_listings.append(listing)

                time.sleep(1)

    return all_listings


def load_seen_listings(data_dir="data"):
    """Load previously seen listing IDs."""
    seen_file = Path(data_dir) / "seen_listings.json"
    if seen_file.exists():
        with open(seen_file, encoding='utf-8-sig') as f:
            return json.load(f)
    return {}


def save_seen_listings(seen, data_dir="data"):
    """Save seen listing IDs."""
    Path(data_dir).mkdir(exist_ok=True)
    seen_file = Path(data_dir) / "seen_listings.json"
    with open(seen_file, 'w', encoding='utf-8') as f:
        json.dump(seen, f, indent=2)


def load_published_listings(data_dir="data"):
    """Load all published listings (the full history)."""
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, encoding='utf-8-sig') as f:
            return json.load(f)
    return {"rounds": []}


def save_published_listings(published, data_dir="data"):
    """Save published listings."""
    Path(data_dir).mkdir(exist_ok=True)
    pub_file = Path(data_dir) / "published_listings.json"
    with open(pub_file, 'w', encoding='utf-8') as f:
        json.dump(published, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    config = load_config()
    print("Running test search...")
    listings = run_search_round(config)
    print(f"\nTotal listings found: {len(listings)}")
    for l in listings[:5]:
        print(f"  - {l['title'][:60]} | {l['portal']} | \u20ac{l.get('price_eur', 'N/A')}")
