"""
Static site generator for Vietnam Property Deal Finder.
Generates a clean HTML page from published listings data.
"""

import json
from datetime import datetime
from pathlib import Path


def generate_site(published, config, output_dir="docs"):
    """Generate the static HTML site from published listings data."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    rounds = published.get('rounds', [])

    # Reverse chronological
    rounds_sorted = sorted(rounds, key=lambda r: r['date'], reverse=True)

    # Location labels
    loc_labels = {k: v['label'] for k, v in config['locations'].items()}

    html = generate_html(rounds_sorted, config, loc_labels)

    output_path = Path(output_dir) / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  Site written to: {output_path}")
    return str(output_path)


def score_color(score):
    """Return CSS color for score badge."""
    if score >= 6:
        return '#16a34a'  # green
    elif score >= 5:
        return '#2563eb'  # blue
    elif score >= 4:
        return '#d97706'  # amber
    else:
        return '#dc2626'  # red


def score_label(score):
    """Return label for score."""
    if score >= 6.5:
        return 'Exceptional'
    elif score >= 6:
        return 'Excellent'
    elif score >= 5.5:
        return 'Very Good'
    elif score >= 5:
        return 'Good Deal'
    elif score >= 4:
        return 'Decent'
    else:
        return 'Below Avg'


def format_price(listing):
    """Format price for display."""
    price = listing.get('parsed_data', {}).get('price_usd') or listing.get('price_usd')
    if price and isinstance(price, (int, float)):
        if price >= 1000:
            return f"${price:,.0f}"
        else:
            return f"${price:.0f}"
    raw = listing.get('price_raw', '')
    if raw:
        return raw
    return 'Price TBD'


def format_size(listing):
    """Format size for display."""
    sqm = listing.get('parsed_data', {}).get('size_sqm') or listing.get('size_sqm')
    if sqm:
        return f"{sqm:.0f} sqm"
    return ''


def format_bedrooms(listing):
    """Format bedrooms for display."""
    br = listing.get('parsed_data', {}).get('bedrooms') or listing.get('bedrooms')
    if br is not None:
        if br == 0:
            return 'Studio'
        return f"{br}BR"
    return ''


def generate_listing_card(listing):
    """Generate HTML for a single listing card."""
    score = listing.get('score', 0)
    color = score_color(score)
    label = score_label(score)
    loc_key = listing.get('location_key', '')
    title = listing.get('title', 'Untitled')[:80]
    url = listing.get('url', '#')
    portal = listing.get('portal', '')
    price = format_price(listing)
    size = format_size(listing)
    bedrooms = format_bedrooms(listing)
    snippet = listing.get('source_snippet', listing.get('description', ''))[:200]
    over_budget = listing.get('parsed_data', {}).get('over_budget', False)

    details = ' \u00b7 '.join(filter(None, [price, bedrooms, size]))
    budget_badge = '<span class="badge badge-warn">Over Budget</span>' if over_budget else ''

    # Component scores tooltip
    components = listing.get('score_components', {})
    tooltip_lines = [f"{k.replace('_', ' ').title()}: {v}/7" for k, v in components.items()]
    tooltip = '&#10;'.join(tooltip_lines)

    return f'''
    <div class="listing-card">
      <div class="card-header">
        <div class="score-badge" style="background:{color}" title="{tooltip}">
          <span class="score-num">{score:.1f}</span>
          <span class="score-label">{label}</span>
        </div>
        <div class="card-title-area">
          <a href="{url}" target="_blank" rel="noopener" class="card-title">{title}</a>
          <div class="card-meta">
            <span class="badge badge-portal">{portal}</span>
            {budget_badge}
          </div>
        </div>
      </div>
      <div class="card-details">{details}</div>
      <p class="card-snippet">{snippet}</p>
    </div>
    '''

def generate_html(rounds, config, loc_labels):
    """Generate the full HTML page."""
    budget = config.get('budget_max_usd', 150000)
    threshold = config.get('score_threshold', 5)
    locations_str = ', '.join(loc_labels.values())

    # Stats
    total_rounds = len(rounds)
    total_listings = sum(r.get('published_count', 0) for r in rounds)
    last_run = rounds[0]['date'] if rounds else 'Never'

    # Build rounds HTML
    rounds_html = ''
    for rnd in rounds:
        date = rnd['date']
        listings = rnd.get('listings', [])
        total_searched = rnd.get('total_searched', 0)
        new_found = rnd.get('new_found', 0)

        if not listings:
            rounds_html += f'''
            <section class="round-section">
              <h2 class="round-date">{date}</h2>
              <p class="round-meta">Searched {total_searched} results \u00b7 {new_found} new \u00b7 No deals scoring {threshold}+ found</p>
            </section>
            '''
            continue

        # Group by location
        by_location = {}
        for l in listings:
            loc = l.get('location_key', 'other')
            by_location.setdefault(loc, []).append(l)

        listings_html = ''
        for loc_key, loc_listings in by_location.items():
            loc_label = loc_labels.get(loc_key, loc_key.replace('_', ' ').title())
            loc_listings.sort(key=lambda x: x.get('score', 0), reverse=True)

            cards = ''.join(generate_listing_card(l) for l in loc_listings)
            listings_html += f'''
            <div class="location-group">
              <h3 class="location-label">{loc_label}</h3>
              {cards}
            </div>
            '''

        rounds_html += f'''
        <section class="round-section">
          <h2 class="round-date">{date}</h2>
          <p class="round-meta">Searched {total_searched} results \u00b7 {new_found} new \u00b7 {len(listings)} sweet deals published</p>
          {listings_html}
        </section>
        '''

    # Scoring methodology HTML
    weights = config.get('scoring_weights', {})
    weights_rows = ''.join(
        f'<tr><td>{k.replace("_", " ").title()}</td><td>{int(v*100)}%</td></tr>'
        for k, v in weights.items()
    )
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vietnam Property Deals</title>
  <style>
    :root {{
      --bg: #0f172a;
      --surface: #1e293b;
      --surface2: #334155;
      --text: #e2e8f0;
      --text-dim: #94a3b8;
      --accent: #38bdf8;
      --green: #16a34a;
      --blue: #2563eb;
      --amber: #d97706;
      --red: #dc2626;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
    }}

    .container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}

    header {{
      text-align: center;
      padding: 3rem 0 2rem;
      border-bottom: 1px solid var(--surface2);
      margin-bottom: 2rem;
    }}

    h1 {{
      font-size: 2rem;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 0.5rem;
    }}

    .subtitle {{
      color: var(--text-dim);
      font-size: 1rem;
    }}

    .stats-bar {{
      display: flex;
      justify-content: center;
      gap: 2rem;
      margin-top: 1.5rem;
      flex-wrap: wrap;
    }}

    .stat {{
      text-align: center;
    }}

    .stat-num {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--accent);
    }}

    .stat-label {{
      font-size: 0.75rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .round-section {{
      margin-bottom: 3rem;
    }}

    .round-date {{
      font-size: 1.3rem;
      font-weight: 700;
      color: var(--accent);
      padding-bottom: 0.5rem;
      border-bottom: 2px solid var(--surface2);
      margin-bottom: 0.5rem;
    }}

    .round-meta {{
      color: var(--text-dim);
      font-size: 0.85rem;
      margin-bottom: 1.5rem;
    }}

    .location-group {{
      margin-bottom: 1.5rem;
    }}

    .location-label {{
      font-size: 1rem;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 0.75rem;
      padding-left: 0.5rem;
      border-left: 3px solid var(--accent);
    }}

    .listing-card {{
      background: var(--surface);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 0.75rem;
      transition: transform 0.15s;
    }}

    .listing-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}

    .card-header {{
      display: flex;
      gap: 1rem;
      align-items: flex-start;
      margin-bottom: 0.5rem;
    }}

    .score-badge {{
      flex-shrink: 0;
      width: 56px;
      height: 56px;
      border-radius: 10px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: white;
      cursor: help;
    }}

    .score-num {{
      font-size: 1.25rem;
      font-weight: 800;
      line-height: 1;
    }}

    .score-label {{
      font-size: 0.55rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      opacity: 0.9;
    }}

    .card-title-area {{
      flex: 1;
      min-width: 0;
    }}

    .card-title {{
      color: var(--text);
      text-decoration: none;
      font-weight: 600;
      font-size: 1rem;
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .card-title:hover {{
      color: var(--accent);
    }}

    .card-meta {{
      display: flex;
      gap: 0.5rem;
      margin-top: 0.25rem;
      flex-wrap: wrap;
    }}

    .badge {{
      font-size: 0.7rem;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      font-weight: 600;
      text-transform: uppercase;
    }}

    .badge-portal {{
      background: var(--surface2);
      color: var(--text-dim);
    }}

    .badge-warn {{
      background: var(--red);
      color: white;
    }}

    .card-details {{
      color: var(--accent);
      font-weight: 600;
      font-size: 0.95rem;
      margin-bottom: 0.4rem;
    }}

    .card-snippet {{
      color: var(--text-dim);
      font-size: 0.85rem;
      line-height: 1.5;
    }}

    .methodology {{
      background: var(--surface);
      border-radius: 10px;
      padding: 1.5rem;
      margin-top: 2rem;
    }}

    .methodology h2 {{
      font-size: 1.1rem;
      margin-bottom: 1rem;
      color: var(--accent);
    }}

    .methodology table {{
      width: 100%;
      border-collapse: collapse;
    }}

    .methodology td {{
      padding: 0.4rem 0.75rem;
      border-bottom: 1px solid var(--surface2);
      font-size: 0.85rem;
    }}

    .methodology td:last-child {{
      text-align: right;
      font-weight: 600;
      color: var(--accent);
    }}

    footer {{
      text-align: center;
      padding: 2rem 0;
      color: var(--text-dim);
      font-size: 0.8rem;
    }}

    .empty-state {{
      text-align: center;
      padding: 4rem 2rem;
      color: var(--text-dim);
    }}

    .empty-state p {{
      font-size: 1.1rem;
      margin-bottom: 0.5rem;
    }}

    @media (max-width: 600px) {{
      .container {{ padding: 1rem; }}
      h1 {{ font-size: 1.5rem; }}
      .stats-bar {{ gap: 1rem; }}
      .card-header {{ flex-direction: column; align-items: stretch; }}
      .score-badge {{
        width: auto;
        height: auto;
        flex-direction: row;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Vietnam Property Deals</h1>
      <p class="subtitle">Daily curated listings \u00b7 Budget: ${budget:,} USD \u00b7 {locations_str}</p>
      <div class="stats-bar">
        <div class="stat">
          <div class="stat-num">{total_rounds}</div>
          <div class="stat-label">Search Rounds</div>
        </div>
        <div class="stat">
          <div class="stat-num">{total_listings}</div>
          <div class="stat-label">Deals Found</div>
        </div>
        <div class="stat">
          <div class="stat-num">{threshold}+/7</div>
          <div class="stat-label">Score Threshold</div>
        </div>
        <div class="stat">
          <div class="stat-num">{last_run}</div>
          <div class="stat-label">Last Run</div>
        </div>
      </div>
    </header>

    <main>
      {rounds_html if rounds_html.strip() else '<div class="empty-state"><p>No search rounds yet.</p><p>The first automated scan will run at 5:00 AM UTC.</p></div>'}
    </main>

    <div class="methodology">
      <h2>Scoring Methodology (1-7 Scale)</h2>
      <table>
        {weights_rows}
      </table>
      <p style="margin-top:1rem;font-size:0.8rem;color:var(--text-dim)">
        Only listings scoring {threshold}+ are published. Over-budget listings receive a 50% score penalty.
      </p>
    </div>

    <footer>
      <p>Vietnam Property Deal Finder \u00b7 Automated daily at 05:00 UTC \u00b7 Data from batdongsan.vn, dotproperty.com.vn, fazwaz.vn, vietnam-real.estate, houseinhanoi.vn, sunset-town.com</p>
    </footer>
  </div>
</body>
</html>'''

if __name__ == '__main__':
    # Test with sample data
    config = json.loads(open('config.json').read())
    sample_published = {
        "rounds": [{
            "date": "2026-03-21",
            "timestamp": "2026-03-21T05:00:00",
            "total_searched": 48,
            "new_found": 12,
            "published_count": 3,
            "listings": [
                {
                    "title": "Sun Grand City Hillside 1BR - An Thoi Phu Quoc",
                    "url": "https://sunset-town.com/en/example",
                    "portal": "sunset-town",
                    "location_key": "phu_quoc",
                    "price_usd": 85000,
                    "size_sqm": 38,
                    "bedrooms": 1,
                    "developer": "Sun Group",
                    "description": "Beachfront 1BR apartment with sea view. Long-term ownership. Santorini design.",
                    "source_snippet": "Beachfront 1BR apartment with sea view. Long-term ownership. Santorini design.",
                    "score": 6.2,
                    "score_components": {
                        "price_per_sqm": 6, "location_tier": 6, "sea_proximity": 7,
                        "growth_potential": 6, "regional_development": 6, "air_quality": 5,
                        "developer_reputation": 6, "foreign_ownership_clarity": 7, "bedroom_criteria_fit": 7
                    },
                    "parsed_data": {"price_usd": 85000, "size_sqm": 38, "bedrooms": 1, "over_budget": false}
                },
                {
                    "title": "Meyhomes Capital 1BR - Duong To Phu Quoc",
                    "url": "https://dotproperty.com.vn/example",
                    "portal": "dotproperty",
                    "location_key": "phu_quoc",
                    "price_usd": 79000,
                    "size_sqm": 32,
                    "bedrooms": 1,
                    "developer": "Meyland",
                    "description": "1BR apartment near Bai Truong beach. Township concept with full amenities.",
                    "source_snippet": "1BR apartment near Bai Truong beach. Township concept with full amenities.",
                    "score": 5.5,
                    "score_components": {
                        "price_per_sqm": 5, "location_tier": 6, "sea_proximity": 5,
                        "growth_potential": 6, "regional_development": 6, "air_quality": 5,
                        "developer_reputation": 5, "foreign_ownership_clarity": 5, "bedroom_criteria_fit": 7
                    },
                    "parsed_data": {"price_usd": 79000, "size_sqm": 32, "bedrooms": 1, "over_budget": false}
                },
                {
                    "title": "9X Quy Nhon 2BR Apartment - Nguyen Van Cu",
                    "url": "https://dotproperty.com.vn/example2",
                    "portal": "dotproperty",
                    "location_key": "quy_nhon",
                    "price_usd": 33000,
                    "size_sqm": 53,
                    "bedrooms": 2,
                    "developer": null,
                    "description": "2BR apartment in Quy Nhon city center. AC, security, car park, balcony.",
                    "source_snippet": "2BR apartment in Quy Nhon city center. AC, security, car park, balcony.",
                    "score": 5.8,
                    "score_components": {
                        "price_per_sqm": 7, "location_tier": 5, "sea_proximity": 3,
                        "growth_potential": 6, "regional_development": 5, "air_quality": 6,
                        "developer_reputation": 3, "foreign_ownership_clarity": 3, "bedroom_criteria_fit": 7
                    },
                    "parsed_data": {"price_usd": 33000, "size_sqm": 53, "bedrooms": 2, "over_budget": false}
                }
            ]
        }]
    }

    generate_site(sample_published, config, "docs")
    print("Test site generated at docs/index.html")