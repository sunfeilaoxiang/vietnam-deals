"""
Static site generator for Vietnam Property Deal Finder.
Generates a clean HTML page in Russian from published listings data.
"""

import json
from datetime import datetime
from pathlib import Path


def generate_site(published, config, output_dir="docs"):
    """Generate the static HTML site from published listings data."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    rounds = published.get('rounds', [])
    rounds_sorted = sorted(rounds, key=lambda r: r['date'], reverse=True)
    loc_labels = {k: v['label'] for k, v in config['locations'].items()}
    html = generate_html(rounds_sorted, config, loc_labels)
    output_path = Path(output_dir) / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Site written to: {output_path}")
    return str(output_path)


def score_color(score):
    if score >= 6:
        return '#16a34a'
    elif score >= 5.5:
        return '#2563eb'
    elif score >= 5:        return '#0891b2'
    elif score >= 4:
        return '#d97706'
    else:
        return '#dc2626'


def score_label(score):
    if score >= 6.5:
        return '\u041e\u0442\u043b\u0438\u0447\u043d\u043e'
    elif score >= 6:
        return '\u041e\u0447. \u0445\u043e\u0440\u043e\u0448\u043e'
    elif score >= 5.5:
        return '\u0425\u043e\u0440\u043e\u0448\u043e'
    elif score >= 5:
        return '\u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e'
    elif score >= 4:
        return '\u0421\u0440\u0435\u0434\u043d\u0435'
    else:
        return '\u041d\u0438\u0436\u0435 \u0441\u0440.'


def format_price(listing):
    price = listing.get('parsed_data', {}).get('price_eur') or listing.get('price_eur')
    if price and isinstance(price, (int, float)):
        if price >= 1000:
            return f"\u20ac{price:,.0f}"
        else:
            return f"\u20ac{price:.0f}"
    raw = listing.get('price_raw', '')    if raw:
        return raw
    return None


def format_size(listing):
    sqm = listing.get('parsed_data', {}).get('size_sqm') or listing.get('size_sqm')
    if sqm:
        return f"{sqm:.0f} \u043c\u00b2"
    return ''


def format_bedrooms(listing):
    br = listing.get('parsed_data', {}).get('bedrooms') or listing.get('bedrooms')
    if br is not None:
        if br == 0:
            return '\u0421\u0442\u0443\u0434\u0438\u044f'
        return f"{br} \u0441\u043f."
    return ''


def format_price_per_sqm(listing):
    price = listing.get('parsed_data', {}).get('price_eur') or listing.get('price_eur')
    sqm = listing.get('parsed_data', {}).get('size_sqm') or listing.get('size_sqm')
    if price and sqm and isinstance(price, (int, float)) and isinstance(sqm, (int, float)) and sqm > 0:
        ppsm = price / sqm
        return f"\u20ac{ppsm:,.0f}/\u043c\u00b2"
    return ''

def generate_listing_card(listing):
    score = listing.get('score', 0)
    color = score_color(score)
    label = score_label(score)
    title = listing.get('title', 'Untitled')[:80]
    url = listing.get('url', '#')
    portal = listing.get('portal', '')
    price = format_price(listing)
    size = format_size(listing)
    bedrooms = format_bedrooms(listing)
    price_per_sqm = format_price_per_sqm(listing)
    snippet = listing.get('source_snippet', listing.get('description', ''))[:200]
    over_budget = listing.get('parsed_data', {}).get('over_budget', False)

    # Format bathrooms
    bathrooms = listing.get('bathrooms')
    bath_str = f"{bathrooms} \u0432\u0430\u043d." if bathrooms else ''

    # Legal status and furnishing
    legal = listing.get('legal_status', '')
    furnishing = listing.get('furnishing', '')

    details = ' \u00b7 '.join(filter(None, [price, bedrooms, bath_str, size, price_per_sqm]))
    budget_badge = '<span class="badge badge-warn">\u0421\u0432\u0435\u0440\u0445 \u0431\u044e\u0434\u0436\u0435\u0442\u0430</span>' if over_budget else ''

    # Property info tags
    info_tags = ''
    if legal:
        info_tags += f'<span class="badge badge-info">{legal}</span>'    if furnishing:
        info_tags += f'<span class="badge badge-info">{furnishing}</span>'
    developer = listing.get('developer', '')
    if developer:
        info_tags += f'<span class="badge badge-dev">{developer}</span>'

    components = listing.get('score_components', {})
    factor_names_ru = {
        'price_per_sqm': '\u0426\u0435\u043d\u0430 \u0437\u0430 \u043c\u00b2',
        'location_tier': '\u041b\u043e\u043a\u0430\u0446\u0438\u044f',
        'sea_proximity': '\u0411\u043b\u0438\u0437\u043e\u0441\u0442\u044c \u043a \u043c\u043e\u0440\u044e',
        'growth_potential': '\u041f\u043e\u0442\u0435\u043d\u0446\u0438\u0430\u043b \u0440\u043e\u0441\u0442\u0430',
        'regional_development': '\u0420\u0430\u0437\u0432\u0438\u0442\u0438\u0435 \u0440\u0435\u0433\u0438\u043e\u043d\u0430',
        'air_quality': '\u041a\u0430\u0447\u0435\u0441\u0442\u0432\u043e \u0432\u043e\u0437\u0434\u0443\u0445\u0430',
        'developer_reputation': '\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f \u0437\u0430\u0441\u0442\u0440\u043e\u0439\u0449\u0438\u043a\u0430',
        'foreign_ownership_clarity': '\u041f\u0440\u0430\u0432\u0430 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u043e\u0441\u0442\u0438',
        'bedroom_criteria_fit': '\u0421\u043f\u0430\u043b\u044c\u043d\u0438'
    }
    tooltip_lines = [f"{factor_names_ru.get(k, k)}: {v}/7" for k, v in components.items()]
    tooltip = '&#10;'.join(tooltip_lines)

    return f'''
    <div class="listing-card">
      <div class="card-header">
        <div class="score-badge" style="background:{color}" title="{tooltip}">
          <span class="score-num">{score:.1f}</span>
          <span class="score-label">{label}</span>
        </div>
        <div class="card-title-area">
          <a href="{url}" target="_blank" rel="noopener" class="card-title">{title}</a>          <div class="card-meta">
            <span class="badge badge-portal">{portal}</span>
            {budget_badge}
          </div>
        </div>
      </div>
      <div class="card-details">{details}</div>
      {f'<div class="card-tags">{info_tags}</div>' if info_tags else ''}
      <p class="card-snippet">{snippet}</p>
    </div>
    '''


def generate_html(rounds, config, loc_labels):
    budget = config.get('budget_max_eur', 140000)
    threshold = config.get('score_threshold', 5.5)
    locations_str = ', '.join(loc_labels.values())

    total_rounds = len(rounds)
    total_listings = sum(r.get('published_count', 0) for r in rounds)
    last_run = rounds[0]['date'] if rounds else '\u041d\u0438\u043a\u043e\u0433\u0434\u0430'

    rounds_html = ''
    for rnd in rounds:
        date = rnd['date']
        listings = rnd.get('listings', [])
        total_searched = rnd.get('total_searched', 0)
        new_found = rnd.get('new_found', 0)

        if not listings:            rounds_html += f'''
            <section class="round-section">
              <h2 class="round-date">{date}</h2>
              <p class="round-meta">\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e {total_searched} \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432 \u00b7 {new_found} \u043d\u043e\u0432\u044b\u0445 \u00b7 \u041d\u0435\u0442 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439 \u0441 \u0440\u0435\u0439\u0442\u0438\u043d\u0433\u043e\u043c {threshold}+</p>
            </section>
            '''
            continue

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
          <p class="round-meta">\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e {total_searched} \u00b7 {new_found} \u043d\u043e\u0432\u044b\u0445 \u00b7 {len(listings)} \u0432\u044b\u0433\u043e\u0434\u043d\u044b\u0445 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439</p>
          {listings_html}
        </section>        '''

    weights = config.get('scoring_weights', {})
    factor_names_ru = {
        'price_per_sqm': '\u0426\u0435\u043d\u0430 \u0437\u0430 \u043c\u00b2',
        'location_tier': '\u041b\u043e\u043a\u0430\u0446\u0438\u044f',
        'sea_proximity': '\u0411\u043b\u0438\u0437\u043e\u0441\u0442\u044c \u043a \u043c\u043e\u0440\u044e',
        'growth_potential': '\u041f\u043e\u0442\u0435\u043d\u0446\u0438\u0430\u043b \u0440\u043e\u0441\u0442\u0430',
        'regional_development': '\u0420\u0430\u0437\u0432\u0438\u0442\u0438\u0435 \u0440\u0435\u0433\u0438\u043e\u043d\u0430',
        'air_quality': '\u041a\u0430\u0447\u0435\u0441\u0442\u0432\u043e \u0432\u043e\u0437\u0434\u0443\u0445\u0430',
        'developer_reputation': '\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f \u0437\u0430\u0441\u0442\u0440\u043e\u0439\u0449\u0438\u043a\u0430',
        'foreign_ownership_clarity': '\u041f\u0440\u0430\u0432\u0430 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u043e\u0441\u0442\u0438',
        'bedroom_criteria_fit': '\u0421\u043f\u0430\u043b\u044c\u043d\u0438'
    }
    weights_rows = ''.join(
        f'<tr><td>{factor_names_ru.get(k, k)}</td><td>{int(v*100)}%</td></tr>'
        for k, v in weights.items()
    )
    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>\u041d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c \u0412\u044c\u0435\u0442\u043d\u0430\u043c\u0430 \u2014 \u041b\u0443\u0447\u0448\u0438\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f</title>
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
      margin: 0 auto;      padding: 2rem 1.5rem;
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
    .stat {{ text-align: center; }}
    .stat-num {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
    .stat-label {{ font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }}
    .round-section {{ margin-bottom: 3rem; }}
    .round-date {{ font-size: 1.3rem; font-weight: 700; color: var(--accent); padding-bottom: 0.5rem; border-bottom: 2px solid var(--surface2); margin-bottom: 0.5rem; }}    .round-meta {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 1.5rem; }}
    .location-group {{ margin-bottom: 1.5rem; }}
    .location-label {{ font-size: 1rem; font-weight: 600; color: var(--text); margin-bottom: 0.75rem; padding-left: 0.5rem; border-left: 3px solid var(--accent); }}
    .listing-card {{ background: var(--surface); border-radius: 10px; padding: 1.25rem; margin-bottom: 0.75rem; transition: transform 0.15s; }}
    .listing-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
    .card-header {{ display: flex; gap: 1rem; align-items: flex-start; margin-bottom: 0.5rem; }}
    .score-badge {{ flex-shrink: 0; width: 56px; height: 56px; border-radius: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; cursor: help; }}
    .score-num {{ font-size: 1.25rem; font-weight: 800; line-height: 1; }}
    .score-label {{ font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.03em; opacity: 0.9; }}
    .card-title-area {{ flex: 1; min-width: 0; }}
    .card-title {{ color: var(--text); text-decoration: none; font-weight: 600; font-size: 1rem; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .card-title:hover {{ color: var(--accent); }}
    .card-meta {{ display: flex; gap: 0.5rem; margin-top: 0.25rem; flex-wrap: wrap; }}
    .badge {{ font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 600; text-transform: uppercase; }}
    .badge-portal {{ background: var(--surface2); color: var(--text-dim); }}
    .badge-warn {{ background: var(--red); color: white; }}
    .badge-info {{ background: rgba(56,189,248,0.15); color: var(--accent); border: 1px solid rgba(56,189,248,0.3); }}
    .badge-dev {{ background: rgba(22,163,74,0.15); color: var(--green); border: 1px solid rgba(22,163,74,0.3); }}
    .card-details {{ color: var(--accent); font-weight: 600; font-size: 0.95rem; margin-bottom: 0.4rem; }}
    .card-tags {{ display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.4rem; }}
    .card-snippet {{ color: var(--text-dim); font-size: 0.85rem; line-height: 1.5; }}
    .methodology {{ background: var(--surface); border-radius: 10px; padding: 1.5rem; margin-top: 2rem; }}
    .methodology h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: var(--accent); }}
    .methodology table {{ width: 100%; border-collapse: collapse; }}
    .methodology td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--surface2); font-size: 0.85rem; }}    .methodology td:last-child {{ text-align: right; font-weight: 600; color: var(--accent); }}
    footer {{ text-align: center; padding: 2rem 0; color: var(--text-dim); font-size: 0.8rem; }}
    .empty-state {{ text-align: center; padding: 4rem 2rem; color: var(--text-dim); }}
    .empty-state p {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
    @media (max-width: 600px) {{
      .container {{ padding: 1rem; }}
      h1 {{ font-size: 1.5rem; }}
      .stats-bar {{ gap: 1rem; }}
      .card-header {{ flex-direction: column; align-items: stretch; }}
      .score-badge {{ width: auto; height: auto; flex-direction: row; gap: 0.5rem; padding: 0.5rem 0.75rem; border-radius: 6px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>\u041d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c \u0412\u044c\u0435\u0442\u043d\u0430\u043c\u0430</h1>
      <p class="subtitle">\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 \u043f\u043e\u0438\u0441\u043a \u00b7 \u0411\u044e\u0434\u0436\u0435\u0442: \u20ac{budget:,} \u00b7 {locations_str}</p>
      <div class="stats-bar">
        <div class="stat">
          <div class="stat-num">{total_rounds}</div>
          <div class="stat-label">\u041f\u043e\u0438\u0441\u043a\u043e\u0432</div>
        </div>
        <div class="stat">
          <div class="stat-num">{total_listings}</div>
          <div class="stat-label">\u041d\u0430\u0439\u0434\u0435\u043d\u043e</div>
        </div>
        <div class="stat">
          <div class="stat-num">{threshold}+/7</div>
          <div class="stat-label">\u041c\u0438\u043d. \u0440\u0435\u0439\u0442\u0438\u043d\u0433</div>        </div>
        <div class="stat">
          <div class="stat-num">{last_run}</div>
          <div class="stat-label">\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0437\u0430\u043f\u0443\u0441\u043a</div>
        </div>
      </div>
    </header>

    <main>
      {rounds_html if rounds_html.strip() else '<div class="empty-state"><p>\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432.</p><p>\u041f\u0435\u0440\u0432\u044b\u0439 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a \u0432 05:00 UTC.</p></div>'}
    </main>

    <div class="methodology">
      <h2>\u041c\u0435\u0442\u043e\u0434\u043e\u043b\u043e\u0433\u0438\u044f \u043e\u0446\u0435\u043d\u043a\u0438 (1\u20137)</h2>
      <table>
        {weights_rows}
      </table>
      <p style="margin-top:1rem;font-size:0.8rem;color:var(--text-dim)">
        \u041f\u0443\u0431\u043b\u0438\u043a\u0443\u044e\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f \u0441 \u0440\u0435\u0439\u0442\u0438\u043d\u0433\u043e\u043c {threshold}+. \u0421\u0432\u0435\u0440\u0445 \u0431\u044e\u0434\u0436\u0435\u0442\u0430 = \u0448\u0442\u0440\u0430\u0444 50%.
      </p>
    </div>

    <footer>
      <p>\u041d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c \u0412\u044c\u0435\u0442\u043d\u0430\u043c\u0430 \u00b7 \u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a \u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u043e \u0432 05:00 UTC</p>
    </footer>
  </div>
</body>
</html>'''


if __name__ == '__main__':
    config = json.loads(open('config.json', encoding='utf-8-sig').read())
    published = load_published_listings()
    generate_site(published, config, "docs")
    print("Site generated at docs/index.html")


def load_published_listings(data_dir="data"):
    pub_file = Path(data_dir) / "published_listings.json"
    if pub_file.exists():
        with open(pub_file, encoding='utf-8-sig') as f:
            return json.load(f)
    return {"rounds": []}