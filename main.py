#!/usr/bin/env python3
"""
Vietnam Property Deal Finder - Main Orchestrator
Runs the daily search, scores listings, deduplicates, and generates the website.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from scorer import score_listing, load_config
from scraper import (
    run_search_round, load_seen_listings, save_seen_listings,
    load_published_listings, save_published_listings, generate_listing_id
)
from site_generator import generate_site


def main():
    print(f"\n{'#'*60}")
    print(f"  Vietnam Property Deal Finder")
    print(f"  Run date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}\n")

    # Load config
    config_path = Path(__file__).parent / "config.json"
    config = load_config(str(config_path))

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    # Load previous state
    seen = load_seen_listings(str(data_dir))
    published = load_published_listings(str(data_dir))

    print(f"Previously seen listings: {len(seen)}")
    print(f"Published rounds: {len(published.get('rounds', []))}")

    # Phase 1: Search
    print("\n--- Phase 1: Searching portals ---")
    raw_listings = run_search_round(config)
    print(f"\nRaw listings found: {len(raw_listings)}")

    # Phase 2: Deduplicate
    print("\n--- Phase 2: Deduplicating ---")
    new_listings = []
    for listing in raw_listings:
        lid = listing.get('listing_id', generate_listing_id(listing))
        if lid not in seen:
            new_listings.append(listing)
            seen[lid] = {
                'first_seen': datetime.now().strftime('%Y-%m-%d'),
                'title': listing.get('title', '')[:80]
            }

    print(f"New unique listings: {len(new_listings)}")

    # Phase 3: Score
    print("\n--- Phase 3: Scoring ---")
    scored_listings = []
    for listing in new_listings:
        try:
            loc_key = listing.get('location_key', '')
            result = score_listing(listing, loc_key, config)

            listing['score'] = result['final_score']
            listing['score_components'] = result['component_scores']
            listing['parsed_data'] = result['parsed']

            scored_listings.append(listing)

            score_display = f"{result['final_score']:.1f}/7"
            budget_flag = " [OVER BUDGET]" if result['parsed'].get('over_budget') else ""
            print(f"  {score_display}{budget_flag} | {listing.get('title', '')[:60]}")
        except Exception as e:
            print(f"  WARNING: Failed to score listing '{listing.get('title', '')[:40]}': {e}")

    # Phase 4: Filter to threshold
    threshold = config.get('score_threshold', 5)
    sweet_deals = [l for l in scored_listings if l['score'] >= threshold]
    sweet_deals.sort(key=lambda x: x['score'], reverse=True)

    print(f"\nSweet deals (score >= {threshold}): {len(sweet_deals)}")

    # Phase 5: Publish
    today = datetime.now().strftime('%Y-%m-%d')

    if sweet_deals:
        round_data = {
            'date': today,
            'timestamp': datetime.now().isoformat(),
            'total_searched': len(raw_listings),
            'new_found': len(new_listings),
            'published_count': len(sweet_deals),
            'listings': sweet_deals
        }
        published.setdefault('rounds', []).append(round_data)
        print(f"\nPublished {len(sweet_deals)} listings for {today}")
    else:
        print(f"\nNo new sweet deals found for {today}")
        # Still record the empty round so we know it ran
        round_data = {
            'date': today,
            'timestamp': datetime.now().isoformat(),
            'total_searched': len(raw_listings),
            'new_found': len(new_listings),
            'published_count': 0,
            'listings': []
        }
        published.setdefault('rounds', []).append(round_data)

    # Save state
    save_seen_listings(seen, str(data_dir))
    save_published_listings(published, str(data_dir))

    # Phase 6: Generate website
    print("\n--- Phase 6: Generating website ---")
    try:
        output_dir = Path(__file__).parent / "docs"  # GitHub Pages serves from /docs
        generate_site(published, config, str(output_dir))
        print(f"\n{'#'*60}")
        print(f"  Done! Site generated at: {output_dir}/index.html")
        print(f"{'#'*60}\n")
    except Exception as e:
        print(f"  WARNING: Site generation failed: {e}")
        print(f"  Data was still saved successfully.")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        print(f"\n{'!'*60}")
        print(f"  FATAL ERROR: {e}")
        print(f"{'!'*60}")
        traceback.print_exc()
        sys.exit(1)
