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
from datetime import datetime
from pathlib import Path


def load_config(config_path="config.json"):
    with open(config_path) as f:
        return json.load(f)


def web_search(query, num_results=10):
    """
    Search the web using SerpAPI (free tier: 100 searches/month)
    or fallback to DuckDuckGo HTML scraping.

    Set SERPAPI_KEY env var for SerpAPI, otherwise uses DuckDuckGo.
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
            # Parse DuckDuckGo Lite results
            link_pattern = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="result-link"[^>]*>([^<]+)</a>', html)
            snippet_pattern = re.findall(r'<td class="result-snippet">([^<]+)</td>', html)

            # Alternative parsing if class-based doesn't work
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


def fetch_page(url, timeout=30):
    """Fetch a web page and return its text content."""
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
        })
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  Fetch error for {url}: {e}")
        return ""

def extract_listing_from_search_result(result, portal_name, location_key, config):
    """
    Extract structured listing data from a search result.
    Uses the title, snippet, and optionally fetches the page.
    """
    title = result.get('title', '')
    snippet = result.get('snippet', '')
    url = result.get('url', '')
    combined = f"{title} {snippet}"

    # Try to extract price
    price_usd = extract_price(combined, config.get('vnd_per_usd', 24000))

    # Try to extract size
    size_sqm = extract_size(combined)

    # Try to extract bedrooms
    bedrooms = extract_bedrooms(combined)

    # Try to extract developer
    developer = extract_developer(combined, config.get('known_developers', {}))

    # Sea proximity from text
    sea_proximity = None

    listing = {
        'title': title,
        'url': url,
        'portal': portal_name,
        'location_key': location_key,
        'price_usd': price_usd,
        'price_raw': extract_raw_price(combined),
        'size_sqm': size_sqm,
        'bedrooms': bedrooms,
        'developer': developer,
        'description': snippet,
        'sea_proximity': sea_proximity,
        'found_date': datetime.now().strftime('%Y-%m-%d'),
        'source_snippet': snippet[:300]
    }

    return listing


def extract_price(text, vnd_per_usd=24000):
    """Extract price in USD from text."""
    text = text.lower()

    # USD patterns
    usd_patterns = [
        r'\$\s*([\d,\.]+)\s*k\b',       # $85k
        r'\$\s*([\d,\.]+)\s*(?:usd)?',   # $85,000 or $85000
        r'([\d,\.]+)\s*(?:usd|us\$)',    # 85000 USD
    ]
    for pat in usd_patterns:
        m = re.search(pat, text)
        if m:
            val = float(m.group(1).replace(',', ''))
            if 'k' in text[m.start():m.end()+2]:
                val *= 1000
            if val < 500:
                val *= 1000
            if 10000 <= val <= 10_000_000:
                return val

    # VND billions
    vnd_bil = re.search(r'([\d,\.]+)\s*(?:t\u1ef7|ty|billion|bil)', text)
    if vnd_bil:
        val = float(vnd_bil.group(1).replace(',', ''))
        return round(val * 1_000_000_000 / (vnd_per_usd * 1000))

    # VND millions
    vnd_mil = re.search(r'([\d,\.]+)\s*(?:tri\u1ec7u|trieu|million)', text)
    if vnd_mil:
        val = float(vnd_mil.group(1).replace(',', ''))
        usd = val * 1_000_000 / (vnd_per_usd * 1000)
        if usd > 1000:
            return round(usd)

    return None


def extract_raw_price(text):
    """Extract raw price string for display."""
    patterns = [
        r'\$[\d,\.]+\s*(?:k|m|usd|million|thousand)?',
        r'[\d,\.]+\s*(?:t\u1ef7|ty|billion|tri\u1ec7u|trieu|million)\s*(?:vnd|\u0111|dong)?',
        r'[\d,\.]+\s*(?:usd|us\$)',
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
    text = text.lower()
    if 'studio' in text:
        return 0
    patterns = [
        r'(\d+)\s*(?:br|bed|bedroom|ph\u00f2ng ng\u1ee7|pn)',
        r'(\d+)\s*(?:-?\s*bed)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
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


def generate_listing_id(listing):
    """Create a unique hash for deduplication."""
    # Use title + URL as primary key
    key = f"{listing.get('title', '')}|{listing.get('url', '')}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]


def is_relevant_result(result, location_key, config):
    """Filter out irrelevant search results."""
    title = result.get('title', '').lower()
    url = result.get('url', '').lower()
    snippet = result.get('snippet', '').lower()
    combined = f"{title} {snippet}"

    # Must contain property-related terms
    property_terms = ['apartment', 'c\u0103n h\u1ed9', 'condo', 'villa', 'property', 'b\u00e1n', 'sale',
                      'bedroom', 'sqm', 'm\u00b2', 'ph\u00f2ng ng\u1ee7', 'resort', 'residence']
    if not any(term in combined for term in property_terms):
        return False

    # Skip news articles, guides, general pages
    skip_terms = ['news', 'tin t\u1ee9c', 'blog', 'guide', 'how to', 'wikipedia', 'youtube']
    if any(term in combined for term in skip_terms):
        return False

    return True


def run_search_round(config):
    """
    Run one complete search round across all locations and portals.
    Returns a list of raw listings.
    """
    all_listings = []
    budget_vnd = config['budget_max_usd'] * config['vnd_per_usd'] * 1000
    budget_vnd_str = f"{budget_vnd/1e9:.1f} t\u1ef7"

    for loc_key, loc_config in config['locations'].items():
        print(f"\n{'='*50}")
        print(f"Searching: {loc_config['label']}")
        print(f"{'='*50}")

        for portal in config['portals']:
            for keyword in loc_config['search_keywords'][:2]:  # Limit to 2 keywords per portal
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
                    listing['listing_id'] = generate_listing_id(listing)
                    all_listings.append(listing)

                # Rate limiting
                time.sleep(1)

    return all_listings


def load_seen_listings(data_dir="data"):
    """Load previously seen listing IDs."""
    seen_file = Path(data_dir) / "seen_listings.json"
    if seen_file.exists():
        with open(seen_file) as f:
            return json.load(f)
    return {}


def save_seen_listings(seen, data_dir="data"):
    """Save seen listing IDs."""
    Path(data_dir).mkdir(exist_ok=True)
    seen_file = Path(data_dir) / "seen_listings.json"
    with open(seen_file, 'w') as f:
        json.dump(seen, f, indent=2)


def load_published_listings(data_dir="data"):
    """Load all published listings (the full history)."""
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file) as f:
            return json.load(f)
    return {"rounds": []}


def save_published_listings(published, data_dir="data"):
    """Save published listings."""
    Path(data_dir).mkdir(exist_ok=True)
    pub_file = Path(data_dir) / "published_listings.json"
    with open(pub_file, 'w') as f:
        json.dump(published, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    config = load_config()
    print("Running test search...")
    listings = run_search_round(config)
    print(f"\nTotal raw listings found: {len(listings)}")
    for l in listings[:5]:
        print(f"  - {l['title'][:60]} | {l['portal']} | ${l.get('price_usd', 'N/A')}")