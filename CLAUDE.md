# Vietnam Deals - Claude Code Context

## Quick Commands
- Trigger pipeline: `py C:\Users\dsdar\vietnam-deals-work\trigger_run.py`
- Check run status: `py C:\Users\dsdar\vietnam-deals-work\check_run.py`
- Upload secret: `py C:\Users\dsdar\vietnam-deals-work\upload_secret.py SECRET_NAME path\to\file.json`
- Update contacts on GitHub: `py C:\Users\dsdar\vietnam-deals-work\update_contacts.py`
- List GitHub secrets: `py C:\Users\dsdar\vietnam-deals-work\check_secrets.py`
- Rebuild dashboard: `py C:\Users\dsdar\vietnam-deals-work\build_dashboard.py`
- Push dashboard to GitHub: `py C:\Users\dsdar\vietnam-deals-work\push_html.py`

## File Structure
- `main.py` / `scraper.py` — Firecrawl property scraper (Phase 1)
- `contact_extractor.py` — Playwright contact extraction (Phase 2)
- `fazwaz_scraper.py` — Playwright FazWaz scraper
- `build_dashboard.py` — Generates outreach_dashboard.html from contacts.json
- `push_html.py` — Pushes docs/outreach_dashboard.html to GitHub
- `data/published_listings.json` — Scraped listings
- `data/contacts.json` — Extracted broker contacts (93+ entries as of 2026-03-23)
- `docs/index.html` — Main deals page (GitHub Pages)
- `docs/outreach_dashboard.html` — Outreach tracker dashboard
- `.github/workflows/daily_scan.yml` — Daily pipeline
- `C:\Users\dsdar\zalo-mcp\outreach_tracker.json` — Local outreach status tracker

## Environment
- Windows 11 — Bash tool often fails. Write `.py` scripts and run with `py script.py`
- Never inline Python in cmd.exe — quotes break. Always write to a .py file first
- Correct Python (has all packages): `C:\Users\dsdar\AppData\Local\Python\pythoncore-3.14-64\python.exe`
  Use `py` shortcut or full path. Default `python` on PATH may lack packages.
- GitHub CLI (`gh`) installed. For API calls, Python urllib + pynacl works as fallback

## Browser Automation
- Use Claude in Chrome (javascript_tool, form_input, navigate) for ALL browser automation
- NEVER use Windows MCP for multi-step browser sequences — focus stealing sends inputs to wrong windows
- Windows MCP only for: one-shot actions, Desktop Commander file operations

## Zalo Automation (chat.zalo.me)
- Zalo React ignores synthetic JS events. Use native setter: `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, val)` + dispatch input event
- Click PARENT elements of button text: `el.parentElement.click()` not `el.click()`
- Send flow: focus contenteditable → set innerText → dispatch input → dispatch Enter keydown
- Phone format for search: local (0903826541) not international (+84903826541)
- Strangers who block messages: Add friend with 150-char note as fallback
- zlapi Python library does NOT work with international phone numbers
- Session expires frequently — check for "Đăng nhập" in page title (needs QR re-scan)
- Zalo account: +37127709900 / zalozalo777

## WhatsApp Automation
- NOT built yet — wa.me links open the desktop app (not a browser tab), making Chrome automation impossible
- Workaround: open web.whatsapp.com directly, search by phone number
- Some brokers only have WhatsApp (not Zalo) — build this as secondary channel

## GitHub Repo
- Owner: sunfeilaoxiang, Repo: vietnam-deals
- PAT: stored in script files in vietnam-deals-work/
- Secrets: BATDONGSAN_COOKIES, DOTPROPERTY_COOKIES, FIRECRAWL_API_KEY
  IMPORTANT: secrets are raw JSON (NOT base64-encoded). Cookie bug fixed 2026-03-23.
- When cookies expire: re-extract via Claude in Chrome javascript_tool on logged-in tab, save to .json, run upload_secret.py
- GitHub Pages serves from docs/ folder (not root — files at root will 404)

## Pipeline Step Order (daily_scan.yml)
CRITICAL — steps must run in this order:
1. Firecrawl scraper (main.py)
2. Install Playwright (`pip install playwright && playwright install chromium`)
3. Decode cookies (write raw JSON to cookies/ dir)
4. FazWaz scraper (fazwaz_scraper.py) — MUST be after Playwright install
5. Contact extractor (contact_extractor.py)
6. Build dashboard (build_dashboard.py)
7. Commit and push

## Scraper Notes
- batdongsan float parsing: Vietnamese comma decimals (49,42 not 49.42) — fixed 2026-03-23
- FazWaz is JS SPA — needs Playwright, not Firecrawl. Search pages need longer wait times
- FazWaz parser KNOWN BUG: price and bedrooms returning "unknown"/None — needs fix
- Contact extractor: cookies written as raw JSON to cookies/ dir, not base64 decoded
- batdongsan province URL suffixes required: Phu Quoc → -kg, Quy Nhon → -bdd, Da Lat → -ldd
- Firecrawl wastes credits on image URLs from dotproperty (proppit.com CDN) — skipped but still cost credits
- Credit optimization opportunity: dedup listings BEFORE Firecrawl Pass 2 (saves 30-50%)

## Outreach (as of 2026-03-23)
- /outreach skill: pulls contacts from GitHub, sends via Zalo Web, tracks status
- /zalo-check skill: scans Zalo for broker replies, sends Telegram notification
- Dashboard: sunfeilaoxiang.github.io/vietnam-deals/outreach_dashboard.html
- Outreach tracker: C:\Users\dsdar\zalo-mcp\outreach_tracker.json
- 5 brokers contacted on 2026-03-23: Thao Nguyen, Anh Tu, Phuong Thuy, Bui Van Thai (friend req), +84978986914
- LIVE LEAD: Anh Tu replied "Hi Sr" — needs follow-up response
- Dashboard improvements pending: pagination, search, status sync after outreach

## Accounts
- Zalo: +37127709900 / zalozalo777
- batdongsan user ID: 5054058
- dotproperty: demetrius.sokolovs@gmail.com
