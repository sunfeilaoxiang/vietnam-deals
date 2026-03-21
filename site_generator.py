"""
Static site generator for Vietnam Property Deal Finder.
Generates a clean HTML page in Russian from published listings data.
All listings from all rounds are merged into one filterable, sortable view.
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
    elif score >= 5:
        return '#0891b2'
    elif score >= 4:
        return '#d97706'
    else:
        return '#dc2626'


def score_label(score):
    if score >= 6.5:
        return 'Отлично'
    elif score >= 6:
        return 'Оч. хорошо'
    elif score >= 5.5:
        return 'Хорошо'
    elif score >= 5:
        return 'Нормально'
    elif score >= 4:
        return 'Средне'
    else:
        return 'Ниже ср.'


def format_price_eur(listing):
    price = listing.get('parsed_data', {}).get('price_eur') or listing.get('price_eur')
    if price and isinstance(price, (int, float)) and price >= 100:
        return price
    return 0


def format_size_sqm(listing):
    sqm = listing.get('parsed_data', {}).get('size_sqm') or listing.get('size_sqm')
    if sqm and isinstance(sqm, (int, float)):
        return sqm
    return 0


def format_bedrooms_num(listing):
    br = listing.get('parsed_data', {}).get('bedrooms') or listing.get('bedrooms')
    if br is not None and isinstance(br, (int, float)):
        return int(br)
    return -1


def price_per_sqm_num(listing):
    price = format_price_eur(listing)
    sqm = format_size_sqm(listing)
    if price > 0 and sqm > 0:
        return round(price / sqm, 0)
    return 0


def merge_all_listings(rounds):
    """Merge all listings from all rounds, keeping the latest occurrence if duplicated."""
    seen_ids = {}
    all_listings = []
    for rnd in rounds:
        date = rnd.get('date', '')
        for listing in rnd.get('listings', []):
            lid = listing.get('listing_id', listing.get('url', ''))
            listing['found_date'] = date
            if lid not in seen_ids:
                seen_ids[lid] = len(all_listings)
                all_listings.append(listing)
            # If already seen, keep the first (newest round) since rounds are sorted desc
    return all_listings


def listing_to_json_data(listing, idx):
    """Convert a listing to a JSON-serializable dict for the JS filter engine."""
    price = format_price_eur(listing)
    sqm = format_size_sqm(listing)
    bedrooms = format_bedrooms_num(listing)
    ppsm = price_per_sqm_num(listing)
    score = listing.get('score', 0)
    return {
        'idx': idx,
        'price': price,
        'sqm': sqm,
        'bedrooms': bedrooms,
        'ppsm': ppsm,
        'score': round(score, 1),
        'location': listing.get('location_key', 'other'),
        'date': listing.get('found_date', ''),
        'over_budget': listing.get('parsed_data', {}).get('over_budget', False)
    }


def generate_listing_card(listing, idx, loc_labels=None):
    score = listing.get('score', 0)
    color = score_color(score)
    label = score_label(score)
    title = listing.get('title', 'Untitled')[:80]
    url = listing.get('url', '#')
    portal = listing.get('portal', '')
    found_date = listing.get('found_date', '')
    location_key = listing.get('location_key', 'other')
    city_label = (loc_labels or {}).get(location_key, location_key.replace('_', ' ').title())
    over_budget = listing.get('parsed_data', {}).get('over_budget', False)

    # Format price
    price_eur = format_price_eur(listing)
    price_str = f"€{price_eur:,.0f}" if price_eur > 0 else ''

    # Format size
    sqm = format_size_sqm(listing)
    size_str = f"{sqm:.0f} м²" if sqm > 0 else ''

    # Format bedrooms
    br = format_bedrooms_num(listing)
    if br == 0:
        bedrooms_str = 'Студия'
    elif br > 0:
        bedrooms_str = f"{br} сп."
    else:
        bedrooms_str = ''

    # Price per sqm
    ppsm = price_per_sqm_num(listing)
    ppsm_str = f"€{ppsm:,.0f}/м²" if ppsm > 0 else ''

    # Bathrooms
    bathrooms = listing.get('bathrooms')
    bath_str = f"{bathrooms} ван." if bathrooms else ''

    # Legal, furnishing, developer
    legal = listing.get('legal_status', '')
    furnishing = listing.get('furnishing', '')
    developer = listing.get('developer', '')

    budget_badge = '<span class="badge badge-warn">Сверх бюджета</span>' if over_budget else ''

    # Build specs grid
    specs = []
    if price_str:
        specs.append(('Цена', price_str))
    if bedrooms_str:
        specs.append(('Спальни', bedrooms_str))
    if bath_str:
        specs.append(('Ванные', bath_str))
    if size_str:
        specs.append(('Площадь', size_str))
    if ppsm_str:
        specs.append(('Цена/м²', ppsm_str))
    if legal:
        specs.append(('Право', legal))
    if furnishing:
        specs.append(('Мебель', furnishing))
    if developer:
        specs.append(('Застройщик', developer))

    specs_html = ''.join(
        f'<div class="spec-item"><span class="spec-label">{lbl}</span><span class="spec-value">{val}</span></div>'
        for lbl, val in specs
    )

    snippet = listing.get('source_snippet', listing.get('description', ''))[:200]

    # Score tooltip
    components = listing.get('score_components', {})
    factor_names_ru = {
        'price_per_sqm': 'Цена за м²',
        'location_tier': 'Локация',
        'sea_proximity': 'Близость к морю',
        'growth_potential': 'Потенциал роста',
        'regional_development': 'Развитие региона',
        'air_quality': 'Качество воздуха',
        'developer_reputation': 'Репутация застройщика',
        'foreign_ownership_clarity': 'Права собственности',
        'bedroom_criteria_fit': 'Спальни'
    }
    tooltip_lines = [f"{factor_names_ru.get(k, k)}: {v}/7" for k, v in components.items()]
    tooltip = '&#10;'.join(tooltip_lines)

    return f'''
    <div class="listing-card" data-idx="{idx}">
      <div class="card-header">
        <div class="score-badge" style="background:{color}" title="{tooltip}">
          <span class="score-num">{score:.1f}</span>
          <span class="score-label">{label}</span>
        </div>
        <div class="card-title-area">
          <a href="{url}" target="_blank" rel="noopener" class="card-title">{title}</a>
          <div class="card-meta">
            <span class="badge badge-city">{city_label}</span>
            <span class="badge badge-portal">{portal}</span>
            <span class="badge badge-date">{found_date}</span>
            {budget_badge}
          </div>
        </div>
      </div>
      <div class="specs-grid">{specs_html}</div>
      <p class="card-snippet">{snippet}</p>
    </div>
    '''


def generate_html(rounds, config, loc_labels):
    budget = config.get('budget_max_eur', 140000)
    threshold = config.get('score_threshold', 5.5)
    locations_str = ', '.join(loc_labels.values())

    total_rounds = len(rounds)
    all_listings = merge_all_listings(rounds)
    total_listings = len(all_listings)
    last_run = rounds[0]['date'] if rounds else 'Никогда'

    # Generate cards HTML grouped by city and JSON data for filtering
    # First group by location
    by_location = {}
    for idx, listing in enumerate(all_listings):
        loc = listing.get('location_key', 'other')
        by_location.setdefault(loc, []).append((idx, listing))

    CITY_PREVIEW = 5  # show top N per city initially
    cards_html = ''
    listings_json = []

    def render_city_section(loc_key, loc_items):
        nonlocal cards_html, listings_json
        loc_label = loc_labels.get(loc_key, loc_key.replace('_', ' ').title())
        loc_items.sort(key=lambda x: x[1].get('score', 0), reverse=True)
        total_in_city = len(loc_items)
        cards_html += f'<div class="city-section" data-city="{loc_key}">'
        cards_html += f'<h2 class="city-header">{loc_label} <span class="city-count">{total_in_city}</span></h2>'
        for i, (idx, listing) in enumerate(loc_items):
            extra_cls = ' city-collapsed' if i >= CITY_PREVIEW else ''
            card = generate_listing_card(listing, idx, loc_labels)
            # Inject extra class into the card div
            if extra_cls:
                card = card.replace('class="listing-card"', f'class="listing-card{extra_cls}"', 1)
            cards_html += card
            listings_json.append(listing_to_json_data(listing, idx))
        if total_in_city > CITY_PREVIEW:
            remaining = total_in_city - CITY_PREVIEW
            cards_html += f'<div class="city-expand-wrap"><button class="city-expand-btn" data-city="{loc_key}">Показать все {total_in_city} ({remaining} скрыто)</button></div>'
        cards_html += '</div>'

    # Render location groups in config order
    loc_order = list(config.get('locations', {}).keys())
    for loc_key in loc_order:
        if loc_key not in by_location:
            continue
        render_city_section(loc_key, by_location[loc_key])
    # Any remaining locations not in config
    for loc_key, loc_items in by_location.items():
        if loc_key in loc_order:
            continue
        render_city_section(loc_key, loc_items)

    # Location filter options
    loc_options = ''
    used_locs = set(l.get('location_key', 'other') for l in all_listings)
    for loc_key in config.get('locations', {}):
        if loc_key in used_locs:
            lbl = loc_labels.get(loc_key, loc_key)
            loc_options += f'<option value="{loc_key}">{lbl}</option>'

    # Weights table
    weights = config.get('scoring_weights', {})
    factor_names_ru = {
        'price_per_sqm': 'Цена за м²',
        'location_tier': 'Локация',
        'sea_proximity': 'Близость к морю',
        'growth_potential': 'Потенциал роста',
        'regional_development': 'Развитие региона',
        'air_quality': 'Качество воздуха',
        'developer_reputation': 'Репутация застройщика',
        'foreign_ownership_clarity': 'Права собственности',
        'bedroom_criteria_fit': 'Спальни'
    }
    weights_rows = ''.join(
        f'<tr><td>{factor_names_ru.get(k, k)}</td><td>{int(v*100)}%</td></tr>'
        for k, v in weights.items()
    )

    listings_json_str = json.dumps(listings_json, ensure_ascii=False)

    empty_state = '<div class="empty-state"><p>Пока нет результатов.</p><p>Первый автоматический поиск в 05:00 UTC.</p></div>'
    main_content = f'<div id="listings-container">{cards_html}</div><div class="load-more-wrap" id="load-more-wrap"><button class="load-more-btn" id="load-more-btn">Показать ещё</button></div>' if all_listings else empty_state

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Недвижимость Вьетнама — Лучшие предложения</title>
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
      margin-bottom: 1.5rem;
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

    /* Filter bar */
    .filter-bar {{
      background: var(--surface);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      align-items: center;
    }}
    .filter-bar label {{
      font-size: 0.8rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-right: 0.25rem;
    }}
    .filter-bar select, .filter-bar input {{
      background: var(--surface2);
      color: var(--text);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 6px;
      padding: 0.4rem 0.6rem;
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
    }}
    .filter-bar select:hover, .filter-bar input:hover {{
      border-color: var(--accent);
    }}
    .filter-group {{
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .sort-btn {{
      background: var(--surface2);
      color: var(--text-dim);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 6px;
      padding: 0.4rem 0.75rem;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .sort-btn:hover {{
      border-color: var(--accent);
      color: var(--text);
    }}
    .sort-btn.active {{
      background: rgba(56,189,248,0.15);
      border-color: var(--accent);
      color: var(--accent);
    }}
    .results-count {{
      font-size: 0.85rem;
      color: var(--text-dim);
      margin-bottom: 1rem;
    }}

    .city-section {{ margin-bottom: 2rem; }}
    .city-header {{ font-size: 1.3rem; font-weight: 700; color: var(--accent); padding-bottom: 0.5rem; border-bottom: 2px solid var(--surface2); margin-bottom: 0.75rem; padding-left: 0.5rem; }}
    .city-header .city-count {{ font-size: 0.85rem; font-weight: 400; color: var(--text-dim); margin-left: 0.5rem; }}
    .city-section.hidden {{ display: none; }}
    .listing-card.city-collapsed {{ display: none; }}
    .city-section.expanded .listing-card.city-collapsed {{ display: block; }}
    .city-expand-wrap {{ text-align: center; margin: 0.5rem 0 1rem; }}
    .city-expand-btn {{ background: transparent; color: var(--accent); border: 1px dashed var(--surface2); border-radius: 6px; padding: 0.5rem 1.5rem; font-size: 0.85rem; cursor: pointer; transition: all 0.15s; }}
    .city-expand-btn:hover {{ border-color: var(--accent); background: rgba(56,189,248,0.08); }}
    .city-section.expanded .city-expand-wrap {{ display: none; }}
    .listing-card {{ background: var(--surface); border-radius: 10px; padding: 1.25rem; margin-bottom: 0.75rem; transition: transform 0.15s; }}
    .listing-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
    .listing-card.hidden {{ display: none; }}
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
    .badge-city {{ background: rgba(22,163,74,0.15); color: var(--green); border: 1px solid rgba(22,163,74,0.3); }}
    .badge-date {{ background: rgba(56,189,248,0.1); color: var(--accent); }}
    .badge-warn {{ background: var(--red); color: white; }}
    .badge-info {{ background: rgba(56,189,248,0.15); color: var(--accent); border: 1px solid rgba(56,189,248,0.3); }}
    .badge-dev {{ background: rgba(22,163,74,0.15); color: var(--green); border: 1px solid rgba(22,163,74,0.3); }}
    .specs-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 0.5rem; margin-bottom: 0.6rem; padding: 0.6rem; background: rgba(255,255,255,0.04); border-radius: 8px; }}
    .spec-item {{ display: flex; flex-direction: column; }}
    .spec-label {{ color: var(--text-dim); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .spec-value {{ color: var(--accent); font-weight: 600; font-size: 0.9rem; }}
    .card-snippet {{ color: var(--text-dim); font-size: 0.85rem; line-height: 1.5; }}
    .methodology {{ background: var(--surface); border-radius: 10px; padding: 1.5rem; margin-top: 2rem; }}
    .methodology h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: var(--accent); }}
    .methodology table {{ width: 100%; border-collapse: collapse; }}
    .methodology td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--surface2); font-size: 0.85rem; }}
    .methodology td:last-child {{ text-align: right; font-weight: 600; color: var(--accent); }}
    footer {{ text-align: center; padding: 2rem 0; color: var(--text-dim); font-size: 0.8rem; }}
    .load-more-wrap {{ text-align: center; margin: 1.5rem 0; }}
    .load-more-btn {{ background: var(--surface2); color: var(--accent); border: 1px solid var(--accent); border-radius: 8px; padding: 0.75rem 2rem; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }}
    .load-more-btn:hover {{ background: rgba(56,189,248,0.15); }}
    .empty-state {{ text-align: center; padding: 4rem 2rem; color: var(--text-dim); }}
    .empty-state p {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
    @media (max-width: 600px) {{
      .container {{ padding: 1rem; }}
      h1 {{ font-size: 1.5rem; }}
      .stats-bar {{ gap: 1rem; }}
      .filter-bar {{ flex-direction: column; align-items: stretch; }}
      .filter-group {{ flex-wrap: wrap; }}
      .card-header {{ flex-direction: column; align-items: stretch; }}
      .score-badge {{ width: auto; height: auto; flex-direction: row; gap: 0.5rem; padding: 0.5rem 0.75rem; border-radius: 6px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Недвижимость Вьетнама</h1>
      <p class="subtitle">Ежедневный поиск · Бюджет: €{budget:,} · {locations_str}</p>
      <div class="stats-bar">
        <div class="stat">
          <div class="stat-num">{total_rounds}</div>
          <div class="stat-label">Поисков</div>
        </div>
        <div class="stat">
          <div class="stat-num">{total_listings}</div>
          <div class="stat-label">Найдено</div>
        </div>
        <div class="stat">
          <div class="stat-num">{threshold}+/7</div>
          <div class="stat-label">Мин. рейтинг</div>
        </div>
        <div class="stat">
          <div class="stat-num">{last_run}</div>
          <div class="stat-label">Последний запуск</div>
        </div>
      </div>
    </header>

    <div class="filter-bar" id="filter-bar">
      <div class="filter-group">
        <label>Город:</label>
        <select id="filter-location">
          <option value="all">Все</option>
          {loc_options}
        </select>
      </div>
      <div class="filter-group">
        <label>Сортировка:</label>
        <button class="sort-btn active" data-sort="score" data-dir="desc">Рейтинг ↓</button>
        <button class="sort-btn" data-sort="price" data-dir="asc">Цена ↑</button>
        <button class="sort-btn" data-sort="price" data-dir="desc">Цена ↓</button>
        <button class="sort-btn" data-sort="sqm" data-dir="desc">м² ↓</button>
        <button class="sort-btn" data-sort="sqm" data-dir="asc">м² ↑</button>
        <button class="sort-btn" data-sort="ppsm" data-dir="asc">€/м² ↑</button>
        <button class="sort-btn" data-sort="ppsm" data-dir="desc">€/м² ↓</button>
        <button class="sort-btn" data-sort="date" data-dir="desc">Новые</button>
      </div>
    </div>

    <div class="results-count" id="results-count">{total_listings} предложений</div>

    <main>
      {main_content}
    </main>

    <div class="methodology">
      <h2>Методология оценки (1–7)</h2>
      <table>
        {weights_rows}
      </table>
      <p style="margin-top:1rem;font-size:0.8rem;color:var(--text-dim)">
        Публикуются только объявления с рейтингом {threshold}+. Сверх бюджета = штраф 50%.
      </p>
    </div>

    <footer>
      <p>Недвижимость Вьетнама · Автоматический поиск ежедневно в 05:00 UTC</p>
    </footer>
  </div>

  <script>
  (function() {{
    var listings = {listings_json_str};
    var container = document.getElementById('listings-container');
    var countEl = document.getElementById('results-count');
    var loadMoreWrap = document.getElementById('load-more-wrap');
    var loadMoreBtn = document.getElementById('load-more-btn');
    if (!container || !listings.length) return;

    var PAGE_SIZE = 20;
    var cards = container.querySelectorAll('.listing-card');
    var citySections = container.querySelectorAll('.city-section');
    var currentSort = 'score';
    var currentDir = 'desc';
    var currentLocation = 'all';
    var shownCount = 0;
    var filteredList = [];
    var flatMode = false; // true when sorting or filtering overrides city view

    // City expand buttons
    document.querySelectorAll('.city-expand-btn').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        var sec = this.closest('.city-section');
        if (sec) sec.classList.add('expanded');
      }});
    }});

    function isCityView() {{
      // City grouped view: default sort (score desc) and no city filter
      return currentSort === 'score' && currentDir === 'desc' && currentLocation === 'all';
    }}

    function applyFilters() {{
      var isFilteringCity = currentLocation !== 'all';
      flatMode = !isCityView();

      // Filter
      filteredList = [];
      for (var i = 0; i < listings.length; i++) {{
        var l = listings[i];
        if (currentLocation !== 'all' && l.location !== currentLocation) continue;
        filteredList.push(l);
      }}

      // Sort (only in non-default mode)
      if (flatMode) {{
        filteredList.sort(function(a, b) {{
          var va = a[currentSort] || 0;
          var vb = b[currentSort] || 0;
          if (currentSort === 'date') {{
            va = a.date || '';
            vb = b.date || '';
            return currentDir === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb);
          }}
          if (currentDir === 'desc') return vb - va;
          return va - vb;
        }});
      }}

      if (flatMode) {{
        // --- FLAT MODE: hide city sections, show paginated flat list ---
        citySections.forEach(function(sec) {{ sec.classList.add('hidden'); }});

        // Hide all cards, remove city-collapsed so pagination controls visibility
        for (var k = 0; k < cards.length; k++) {{
          cards[k].classList.add('hidden');
          cards[k].classList.remove('city-collapsed');
        }}

        // Move cards into flat order in container
        for (var j = 0; j < filteredList.length; j++) {{
          container.appendChild(cards[filteredList[j].idx]);
        }}

        // Paginate
        shownCount = 0;
        showMore();
      }} else {{
        // --- CITY VIEW: show city sections with 5 preview + expand ---
        // Restore city-collapsed classes and show city sections
        citySections.forEach(function(sec) {{
          sec.classList.remove('hidden');
          sec.classList.remove('expanded');
          // Move cards back into their city sections
          var city = sec.getAttribute('data-city');
          var cityCards = sec.querySelectorAll('.listing-card');
          // Re-apply city-collapsed to cards beyond preview
          var count = 0;
          for (var c = 0; c < cityCards.length; c++) {{
            cityCards[c].classList.remove('hidden');
            if (count >= 5) {{
              cityCards[c].classList.add('city-collapsed');
            }} else {{
              cityCards[c].classList.remove('city-collapsed');
            }}
            count++;
          }}
        }});

        // Hide load-more in city view
        if (loadMoreWrap) loadMoreWrap.style.display = 'none';
      }}

      countEl.textContent = filteredList.length + ' предложений';
    }}

    function showMore() {{
      var end = Math.min(shownCount + PAGE_SIZE, filteredList.length);
      for (var i = shownCount; i < end; i++) {{
        cards[filteredList[i].idx].classList.remove('hidden');
      }}
      shownCount = end;
      if (loadMoreWrap) {{
        loadMoreWrap.style.display = shownCount >= filteredList.length ? 'none' : 'block';
      }}
      if (loadMoreBtn) {{
        var remaining = filteredList.length - shownCount;
        loadMoreBtn.textContent = 'Показать ещё (' + remaining + ' осталось)';
      }}
    }}

    // Load more button
    if (loadMoreBtn) {{
      loadMoreBtn.addEventListener('click', showMore);
    }}

    // Location filter
    document.getElementById('filter-location').addEventListener('change', function() {{
      currentLocation = this.value;
      applyFilters();
    }});

    // Sort buttons
    var btns = document.querySelectorAll('.sort-btn');
    btns.forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        btns.forEach(function(b) {{ b.classList.remove('active'); }});
        this.classList.add('active');
        currentSort = this.getAttribute('data-sort');
        currentDir = this.getAttribute('data-dir');
        applyFilters();
      }});
    }});

    // No initial applyFilters needed — HTML already renders city view correctly
  }})();
  </script>
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
