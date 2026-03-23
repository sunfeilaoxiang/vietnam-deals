# Vietnam Deals — Claude Code Context

## THIS MACHINE: Windows 11 gotchas
- **No Bash tool** — write `.py` files and run with `py script.py` or full path
- **Never inline Python in cmd.exe** — quotes break. Always write to a file first
- **Python with packages**: `C:\Users\dsdar\AppData\Local\Python\pythoncore-3.14-64\python.exe` (or `py`)
- **Browser automation**: Claude in Chrome ONLY (its own Chrome profile, separate from user's). Windows MCP steals focus and breaks multi-step flows.

## Repo
- Owner: `sunfeilaoxiang`, Repo: `vietnam-deals`
- PAT: stored in `push_html.py` and other scripts in `vietnam-deals-work/`
- GitHub Pages: served from `docs/` folder (not root)
- GitHub Secrets: `BATDONGSAN_COOKIES`, `DOTPROPERTY_COOKIES`, `FIRECRAWL_API_KEY` — all raw JSON, NOT base64

## Pipeline (daily_scan.yml) — step order is critical
1. Firecrawl scraper (`main.py`)
2. `pip install playwright && playwright install chromium`
3. Decode cookies — write raw JSON to `cookies/` dir
4. FazWaz scraper (`fazwaz_scraper.py`) — must come after Playwright install
5. Contact extractor (`contact_extractor.py`)
6. Build + push dashboard (`build_dashboard.py` then `push_html.py`)
7. Commit & push

## Key Scripts
- `trigger_run.py` — trigger GitHub Actions pipeline
- `check_run.py` — check latest run status
- `upload_secret.py NAME path/file.json` — upload GitHub secret
- `build_dashboard.py` — generate outreach_dashboard.html
- `push_html.py` — push docs/ to GitHub
- `whatsapp_outreach.py` — WhatsApp batch outreach

## Data
- `data/published_listings.json` — scored listings from scraper
- `data/contacts.json` — ~103 contacts; ~32 have `broker_phone_full=true` (full unmasked phone) as of 2026-03-23
- `C:\Users\dsdar\zalo-mcp\outreach_tracker.json` — local send tracker (Zalo + WhatsApp)

## Geographic Scope (ALL in scope)
Phu Quoc, Quy Nhon, Da Lat, Con Dao, Da Nang, Ho Chi Minh

## Scraper Quirks
- **batdongsan URL suffixes**: Phu Quoc `-kg`, Quy Nhon `-bdd`, Da Lat `-ldd` — required or redirects to wrong page
- **batdongsan phone quota**: daily per-account limit (~24 reveals/day). Cookies do NOT bypass. Workaround: browser agent manually clicks "Hien so". Got 24 phones 2026-03-23; listings #25-38 still pending.
- **FazWaz**: JS SPA — Playwright only (not Firecrawl). Cookie popup blocks results; use extra wait time.
- **FazWaz parser bug**: price + bedrooms returning "unknown"/None — fix pushed 2026-03-23, unverified.
- **Firecrawl credit leak**: dotproperty image CDN URLs waste credits. Dedup BEFORE Pass 2 saves 30-50%.

## Zalo Outreach (/outreach skill)
- Sends via Zalo Web (`chat.zalo.me`) using Claude in Chrome JS
- Phone format: local `0903826541`, NOT international `+84903826541`
- Zalo ignores synthetic events — use native setter + dispatch `input` event
- Click parents: `el.parentElement.click()` not `el.click()`
- If stranger blocks: Add friend fallback (150-char note in textarea)
- Session expires often — check for "Dang nhap" in title (needs QR re-scan)
- Zalo account: `+37127709900` / `zalozalo777`
- 5 brokers messaged 2026-03-23; **Anh Tu replied "Hi Sr" — follow up needed**

## WhatsApp Outreach (/whatsapp-outreach skill) — LIVE as of 2026-03-23
WhatsApp Web already logged in the Claude in Chrome profile. No QR scan needed.

Proven send flow — do not deviate:
1. Find tab with `web.whatsapp.com` via `tabs_context_mcp`
2. Navigate to `https://web.whatsapp.com/send?phone=84XXXXXXXXX&text=<url_encoded>`
   - Phone: `"84" + broker_phone.lstrip("0")`
   - Encode: `urllib.parse.quote(message_text)`
3. Wait 7 seconds
4. Click (1243, 541) — send button
5. Wait 3 seconds, screenshot to verify, update tracker

CRITICAL: Only one WhatsApp tab at a time. Multiple tabs = session conflict = nothing sends.

~25 phones queued, batch not yet fired — priority for next session.

## Dashboard
Live: `sunfeilaoxiang.github.io/vietnam-deals/outreach_dashboard.html`
Pending: pagination, search, BR/m2 columns, status sync post-outreach

## Accounts
- batdongsan user ID: `5054058`
- dotproperty: `demetrius.sokolovs@gmail.com`
- Zalo: `+37127709900` / `zalozalo777`
