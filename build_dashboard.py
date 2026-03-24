#!/usr/bin/env python3
"""
Build outreach dashboard HTML from contacts.json
Runs as Step 3 in GitHub Actions after scraper and contact extractor.
Also runnable locally.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def build_dashboard(data_dir="data", output_dir="."):
    contacts_file = Path(data_dir) / "contacts.json"
    if not contacts_file.exists():
        print("No contacts.json found, skipping dashboard build")
        return

    with open(contacts_file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    contacts = data.get("contacts", {})

    rows = []
    for lid, c in contacts.items():
        title = (c.get("listing_title") or "")[:80]

        # Extract bedrooms from title or fields
        bedrooms = c.get("bedrooms") or ""
        if not bedrooms:
            import re
            br_match = re.search(r'(\d)\s*(?:BR|PN|phòng ngủ|bedroom|pn)', title, re.IGNORECASE)
            if br_match:
                bedrooms = br_match.group(1)
            elif 'studio' in title.lower():
                bedrooms = "S"
            elif '1PN' in title or '1pn' in title:
                bedrooms = "1"
            elif '2PN' in title or '2pn' in title:
                bedrooms = "2"
            elif '3PN' in title or '3pn' in title:
                bedrooms = "3"

        # Extract area from title or fields
        area = c.get("area") or ""
        if not area:
            area_match = re.search(r'(\d{2,3})\s*m[2²]', title, re.IGNORECASE)
            if area_match:
                area = area_match.group(1)

        rows.append({
            "listing_id": lid,
            "contact_id": lid[:8],
            "broker_name": c.get("broker_name") or "",
            "broker_phone": c.get("broker_phone") or "",
            "phone_full": c.get("broker_phone_full", False),
            "zalo_url": c.get("zalo_url") or "",
            "whatsapp_url": c.get("whatsapp_url") or "",
            "contact_method": c.get("contact_method") or "",
            "portal": c.get("portal") or "",
            "location": c.get("location", ""),
            "price_eur": c.get("price_eur"),
            "listing_title": title,
            "listing_url": c.get("listing_url") or "",
            "listing_score": c.get("listing_score", 0),
            "outreach_status": c.get("outreach_status") or "pending",
            "outreach_date": c.get("outreach_date") or "",
            "outreach_channel": c.get("outreach_channel") or "",
            "response_date": c.get("response_date") or "",
            "response_notes": c.get("response_notes") or "",
            "source": c.get("source") or "",
            "bedrooms": bedrooms,
            "area": area,
        })

    rows.sort(key=lambda x: x.get("listing_score", 0), reverse=True)

    loc_map = {
        "phu_quoc": "Phu Quoc",
        "quy_nhon": "Quy Nhon",
        "da_lat": "Da Lat",
        "con_dao": "Con Dao",
        "vung_tau": "Vung Tau",
    }

    total = len(rows)
    contacted = sum(1 for r in rows if r["outreach_status"] == "contacted")
    responded = sum(1 for r in rows if r["outreach_status"] == "responded")
    meetings = sum(1 for r in rows if r["outreach_status"] == "meeting")
    pending = sum(1 for r in rows if r["outreach_status"] == "pending")
    actionable = sum(1 for r in rows if r["zalo_url"] or r["phone_full"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    # Build table rows
    table_rows = ""
    for r in rows:
        score = r["listing_score"] or 0
        score_class = "score-high" if score >= 5 else ("score-mid" if score >= 3 else "score-low")
        loc = loc_map.get(r["location"], r["location"] or "—")
        price = f"€{r['price_eur']:,.0f}" if r["price_eur"] else "—"

        broker = r["broker_name"]
        if broker and (len(broker) > 30 or not broker.isprintable()):
            broker = broker[:30] if broker.isprintable() else "—"
        if not broker:
            broker = "—"

        phone_class = "phone-full" if r["phone_full"] else "phone-masked"
        status = r["outreach_status"]

        method = r["contact_method"]
        channel = {"zalo": "Zalo", "whatsapp": "WhatsApp", "form": "Form", "phone_masked": "Phone"}.get(method, method or "—")

        links = []
        if r["listing_url"]:
            links.append(f'<a href="{r["listing_url"]}" target="_blank">Listing</a>')
        if r["zalo_url"]:
            links.append(f'<a href="{r["zalo_url"]}" target="_blank">Zalo</a>')
        if r["whatsapp_url"]:
            links.append(f'<a href="{r["whatsapp_url"]}" target="_blank">WA</a>')
        links_html = " ".join(links) if links else "—"

        title_safe = r["listing_title"].replace('"', '&quot;').replace('<', '&lt;')
        title_html = f'<a href="{r["listing_url"]}" target="_blank">{title_safe}</a>' if r["listing_url"] else title_safe

        # Source badge
        source = r.get("source", "")
        if "excel" in source or r["portal"] == "excel":
            source_html = '<span class="source-badge source-excel">Excel</span>'
        elif "manual" in source:
            source_html = '<span class="source-badge source-manual">Manual</span>'
        else:
            source_html = f'<span class="source-badge source-scraper">{r["portal"][:8]}</span>'

        br_display = r["bedrooms"] or "—"
        area_display = f'{r["area"]}m²' if r["area"] else "—"

        contact_id = r["contact_id"]
        table_rows += f'''<tr data-status="{status}">
    <td><span class="score-badge {score_class}">{score:.1f}</span></td>
    <td class="location">{loc}</td>
    <td class="listing-title">{title_html}</td>
    <td style="text-align:center">{br_display}</td>
    <td style="text-align:right">{area_display}</td>
    <td class="price">{price}</td>
    <td class="broker-name">{broker}</td>
    <td class="{phone_class}">{r["broker_phone"]}</td>
    <td>{channel}</td>
    <td><span class="status-badge status-{status}">{status}</span></td>
    <td>{source_html}</td>
    <td class="contact-id">{contact_id}</td>
    <td class="contact-links">{links_html}</td>
</tr>
'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vietnam Property Outreach Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a; color: #e2e8f0; padding: 20px;
}}
h1 {{ color: #f8fafc; margin-bottom: 8px; font-size: 24px; }}
.subtitle {{ color: #94a3b8; margin-bottom: 20px; font-size: 14px; }}
.stats-bar {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.stat-card {{ background: #1e293b; border-radius: 8px; padding: 16px 24px; min-width: 140px; }}
.stat-card .label {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; }}
.stat-card .value {{ color: #f8fafc; font-size: 28px; font-weight: 700; margin-top: 4px; }}
.stat-card .value.green {{ color: #10b981; }}
.stat-card .value.blue {{ color: #3b82f6; }}
.stat-card .value.yellow {{ color: #f59e0b; }}
.filters {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
.filter-btn {{
    background: #1e293b; border: 1px solid #334155; color: #94a3b8;
    padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
}}
.filter-btn.active {{ background: #3b82f6; color: white; border-color: #3b82f6; }}
.filter-btn:hover {{ border-color: #60a5fa; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead th {{
    background: #1e293b; color: #94a3b8; padding: 10px 12px; text-align: left;
    position: sticky; top: 0; cursor: pointer; user-select: none;
    border-bottom: 2px solid #334155; font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px;
}}
thead th:hover {{ color: #e2e8f0; }}
tbody tr {{ border-bottom: 1px solid #1e293b; }}
tbody tr:hover {{ background: #1e293b; }}
td {{ padding: 10px 12px; vertical-align: middle; }}
.score-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-weight: 700; font-size: 13px; min-width: 32px; text-align: center;
}}
.score-high {{ background: #065f46; color: #6ee7b7; }}
.score-mid {{ background: #854d0e; color: #fde68a; }}
.score-low {{ background: #7f1d1d; color: #fca5a5; }}
.status-badge {{
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600; text-transform: uppercase;
}}
.status-pending {{ background: #374151; color: #9ca3af; }}
.status-contacted {{ background: #1e3a5f; color: #60a5fa; }}
.status-responded {{ background: #064e3b; color: #6ee7b7; }}
.status-meeting {{ background: #78350f; color: #fde68a; }}
.status-rejected {{ background: #7f1d1d; color: #fca5a5; }}
.status-error {{ background: #1f2937; color: #6b7280; }}
.broker-name {{ font-weight: 500; color: #f8fafc; }}
.listing-title {{ color: #94a3b8; font-size: 12px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.listing-title a {{ color: #60a5fa; text-decoration: none; }}
.listing-title a:hover {{ text-decoration: underline; }}
.location {{ color: #c084fc; font-weight: 500; }}
.price {{ color: #fbbf24; font-weight: 500; }}
.contact-links a {{ color: #60a5fa; text-decoration: none; margin-right: 8px; font-size: 12px; }}
.contact-links a:hover {{ text-decoration: underline; }}
.phone-masked {{ color: #6b7280; font-style: italic; }}
.phone-full {{ color: #10b981; }}
.last-updated {{ color: #475569; font-size: 12px; margin-top: 16px; }}
.search-bar {{ margin-bottom: 16px; display: flex; gap: 12px; align-items: center; }}
.search-bar input {{
    background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
    padding: 8px 14px; border-radius: 6px; font-size: 13px; width: 300px;
}}
.search-bar input:focus {{ outline: none; border-color: #3b82f6; }}
.search-bar .count {{ color: #64748b; font-size: 13px; }}
.pagination {{
    display: flex; gap: 8px; align-items: center; margin-top: 16px; margin-bottom: 8px;
}}
.pagination button {{
    background: #1e293b; border: 1px solid #334155; color: #94a3b8;
    padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
}}
.pagination button:hover {{ border-color: #60a5fa; color: #e2e8f0; }}
.pagination button:disabled {{ opacity: 0.3; cursor: default; }}
.pagination .page-info {{ color: #64748b; font-size: 13px; }}
.source-badge {{
    display: inline-block; padding: 2px 6px; border-radius: 4px;
    font-size: 10px; font-weight: 600; text-transform: uppercase;
}}
.source-scraper {{ background: #1e3a5f; color: #60a5fa; }}
.source-excel {{ background: #3b1764; color: #c084fc; }}
.source-manual {{ background: #064e3b; color: #6ee7b7; }}
.contact-id {{ color: #475569; font-family: monospace; font-size: 11px; }}
</style>
</head>
<body>
<h1>Vietnam Property Outreach</h1>
<p class="subtitle">Broker contact tracker &mdash; updated {{now}}</p>

<div class="stats-bar">
    <div class="stat-card"><div class="label">Total Listings</div><div class="value">{{total}}</div></div>
    <div class="stat-card"><div class="label">Actionable</div><div class="value blue">{{actionable}}</div></div>
    <div class="stat-card"><div class="label">Contacted</div><div class="value blue">{{contacted}}</div></div>
    <div class="stat-card"><div class="label">Responded</div><div class="value green">{{responded}}</div></div>
    <div class="stat-card"><div class="label">Meetings</div><div class="value yellow">{{meetings}}</div></div>
    <div class="stat-card"><div class="label">Pending</div><div class="value">{{pending}}</div></div>
</div>

<div class="filters">
    <button class="filter-btn active" onclick="filterStatus('all')">All</button>
    <button class="filter-btn" onclick="filterStatus('pending')">Pending</button>
    <button class="filter-btn" onclick="filterStatus('contacted')">Contacted</button>
    <button class="filter-btn" onclick="filterStatus('responded')">Responded</button>
    <button class="filter-btn" onclick="filterStatus('meeting')">Meeting</button>
</div>

<div class="search-bar">
    <input type="text" id="searchBox" placeholder="Search listings, brokers, cities..." oninput="applyFilters()">
    <span class="count" id="visibleCount"></span>
</div>

<div class="pagination" id="paginationTop">
    <button onclick="changePage(-1)" id="prevBtn">Prev</button>
    <span class="page-info" id="pageInfo">Page 1</span>
    <button onclick="changePage(1)" id="nextBtn">Next</button>
    <select onchange="changePageSize(this.value)" style="background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 8px;border-radius:4px;font-size:12px;">
        <option value="25">25 per page</option>
        <option value="50">50 per page</option>
        <option value="100">100 per page</option>
        <option value="999">Show all</option>
    </select>
</div>

<table id="dashboard">
<thead>
<tr>
    <th onclick="sortTable(0)">Score</th>
    <th onclick="sortTable(1)">City</th>
    <th onclick="sortTable(2)">Listing</th>
    <th onclick="sortTable(3)">BR</th>
    <th onclick="sortTable(4)">m²</th>
    <th onclick="sortTable(5)">Price (EUR)</th>
    <th onclick="sortTable(6)">Broker</th>
    <th onclick="sortTable(7)">Phone</th>
    <th onclick="sortTable(8)">Channel</th>
    <th onclick="sortTable(9)">Status</th>
    <th onclick="sortTable(10)">Source</th>
    <th onclick="sortTable(11)">ID</th>
    <th>Links</th>
</tr>
</thead>
<tbody>
{{table_rows}}
</tbody>
</table>

<p class="last-updated">Data from contacts.json &mdash; {{now}}</p>

<script>
let currentPage = 1;
let pageSize = 25;
let currentStatus = 'all';
let searchQuery = '';

function getFilteredRows() {{
    const rows = Array.from(document.querySelectorAll('#dashboard tbody tr'));
    return rows.filter(row => {{
        const statusMatch = currentStatus === 'all' || row.dataset.status === currentStatus;
        const text = row.innerText.toLowerCase();
        const searchMatch = !searchQuery || text.includes(searchQuery.toLowerCase());
        return statusMatch && searchMatch;
    }});
}}

function applyFilters() {{
    searchQuery = document.getElementById('searchBox').value;
    currentPage = 1;
    renderPage();
}}

function filterStatus(status) {{
    currentStatus = status;
    currentPage = 1;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderPage();
}}

function renderPage() {{
    const allRows = Array.from(document.querySelectorAll('#dashboard tbody tr'));
    const filtered = getFilteredRows();
    const totalPages = Math.ceil(filtered.length / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;

    allRows.forEach(r => r.style.display = 'none');
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    filtered.slice(start, end).forEach(r => r.style.display = '');

    document.getElementById('pageInfo').textContent = `Page ${{currentPage}} of ${{totalPages}}`;
    document.getElementById('prevBtn').disabled = currentPage <= 1;
    document.getElementById('nextBtn').disabled = currentPage >= totalPages;
    document.getElementById('visibleCount').textContent = `${{filtered.length}} of ${{allRows.length}} listings`;
}}

function changePage(delta) {{
    currentPage += delta;
    renderPage();
}}

function changePageSize(size) {{
    pageSize = parseInt(size);
    currentPage = 1;
    renderPage();
}}

let sortDir = {{}};
function sortTable(col) {{
    const tbody = document.querySelector('#dashboard tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    sortDir[col] = !sortDir[col];
    rows.sort((a, b) => {{
        let aVal = a.cells[col].innerText;
        let bVal = b.cells[col].innerText;
        let aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
        let bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
        if (!isNaN(aNum) && !isNaN(bNum)) {{
            return sortDir[col] ? aNum - bNum : bNum - aNum;
        }}
        return sortDir[col] ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }});
    rows.forEach(r => tbody.appendChild(r));
    renderPage();
}}

// Init
renderPage();
</script>
</body>
</html>'''

    out_path = Path(output_dir) / "outreach_dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard: {out_path}")
    print(f"  {total} listings | {actionable} actionable | {contacted} contacted | {responded} responded")


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", "data")
    output_dir = os.environ.get("OUTPUT_DIR", ".")
    build_dashboard(data_dir, output_dir)
