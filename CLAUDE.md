# Vietnam Deals - Claude Code Context

## Environment
- Windows 11, Git Bash shell — Bash tool often fails. Write `.py` scripts and run with `py script.py`
- Never inline Python in cmd.exe — quotes break. Always write to a .py file first
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

## GitHub Repo
- Owner: sunfeilaoxiang, Repo: vietnam-deals
- PAT available for API operations
- Secrets: BATDONGSAN_COOKIES, DOTPROPERTY_COOKIES, FIRECRAWL_API_KEY (raw JSON, NOT base64)
- GitHub Pages serves from docs/ folder
- Pipeline: daily_scan.yml runs at 05:00 UTC — Firecrawl scrape → Playwright contacts → FazWaz → dashboard build
- Helper scripts in vietnam-deals-work/: upload_secret.py, trigger_run.py, check_run.py, update_contacts.py

## Scraper Notes
- batdongsan float parsing fails on Vietnamese comma decimals (49,42 not 49.42) — known bug
- FazWaz is JS SPA — needs Playwright, not Firecrawl. Search pages need longer wait times
- Contact extractor: cookies written as raw JSON to cookies/ dir, not base64 decoded
- Firecrawl wastes credits on image URLs from dotproperty (proppit.com CDN) — these get skipped but still cost credits

## Outreach
- /outreach skill: pulls contacts from GitHub, sends via Zalo Web, tracks status
- /zalo-check skill: scans Zalo for broker replies, sends Telegram notification
- Dashboard: sunfeilaoxiang.github.io/vietnam-deals/outreach_dashboard.html
- Outreach tracker: C:\Users\dsdar\zalo-mcp\outreach_tracker.json
