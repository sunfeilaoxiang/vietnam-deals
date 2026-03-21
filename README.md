# Vietnam Property Deal Finder

Automated daily scanner that finds, scores, and publishes the best Vietnam property deals.

## Setup (5 minutes)

### 1. Create the GitHub repo

Go to https://github.com/new and create a new repo:
- Name: `vietnam-deals`
- Make it **Public** (required for free GitHub Pages)
- Do NOT initialize with README (we'll push our own)

### 2. Push this code

```bash
cd vietnam-deals
git init
git add .
git commit -m "Initial setup"
git branch -M main
git remote add origin https://github.com/demetrius-sokolovs/vietnam-deals.git
git push -u origin main
```

### 3. Enable GitHub Pages

1. Go to your repo -> **Settings** -> **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/docs`
4. Click Save

Your site will be live at: `https://demetrius-sokolovs.github.io/vietnam-deals/`

### 4. (Optional) Add SerpAPI key for better search

The scanner works without any API key (uses DuckDuckGo). For better results:

1. Get a free key at https://serpapi.com (100 searches/month free)
2. Go to your repo -> **Settings** -> **Secrets and variables** -> **Actions**
3. Click **New repository secret**
4. Name: `SERPAPI_KEY`, Value: your key

### 5. Enable Actions

1. Go to your repo -> **Actions** tab
2. Click "I understand my workflows, go ahead and enable them"
3. The scan runs automatically at 5:00 AM UTC daily
4. To trigger manually: Actions -> Daily Property Scan -> Run workflow

## How it works

- **Scraper** searches 6 Vietnamese property portals daily
- **Scorer** rates each listing 1-7 based on weighted criteria
- **Deduplicator** skips previously seen listings
- **Site Generator** builds a clean HTML feed
- **GitHub Actions** runs it all at 5 AM and publishes to GitHub Pages

## Configuration

Edit `config.json` to change:
- Budget, locations, bedroom requirements
- Scoring weights
- Search portals and keywords
- Developer reputation tiers

## Scoring weights

| Factor | Weight |
|--------|--------|
| Price per sqm | 20% |
| Location tier | 15% |
| Sea/beach proximity | 15% |
| Growth potential 2030 | 15% |
| Regional development | 10% |
| Developer reputation | 10% |
| Air quality | 5% |
| Foreign ownership clarity | 5% |
| Bedroom criteria fit | 5% |