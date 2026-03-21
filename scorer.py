"""
Vietnam Property Deal Scorer
Weighted scoring system (1-7 scale) for evaluating property listings.
"""

import json
import re
from pathlib import Path


def load_config(config_path="config.json"):
    with open(config_path) as f:
        return json.load(f)


def parse_price_usd(price_str, vnd_per_usd=24000):
    """Extract USD price from various formats."""
    if not price_str:
        return None

    price_str = str(price_str).lower().strip()

    # Direct USD
    usd_match = re.search(r'\$\s*([\d,\.]+)\s*(k|m|million|thousand)?', price_str)
    if usd_match:
        val = float(usd_match.group(1).replace(',', ''))
        suffix = usd_match.group(2) or ''
        if suffix in ('k', 'thousand'):
            val *= 1000
        elif suffix in ('m', 'million'):
            val *= 1_000_000
        return val

    # USD with keyword
    usd_match2 = re.search(r'([\d,\.]+)\s*(usd|us\$)', price_str)
    if usd_match2:
        val = float(usd_match2.group(1).replace(',', ''))
        if val < 1000:
            val *= 1000  # likely in thousands
        return val

    # VND (billion)
    vnd_match = re.search(r'([\d,\.]+)\s*(t\u1ef7|ty|billion|bil)\b', price_str)
    if vnd_match:
        val = float(vnd_match.group(1).replace(',', ''))
        vnd_amount = val * 1_000_000_000
        return vnd_amount / (vnd_per_usd * 1000)

    # VND (trieu / million VND)
    vnd_match2 = re.search(r'([\d,\.]+)\s*(tri\u1ec7u|trieu|million vnd|tr)\b', price_str)
    if vnd_match2:
        val = float(vnd_match2.group(1).replace(',', ''))
        vnd_amount = val * 1_000_000
        return vnd_amount / (vnd_per_usd * 1000)

    # Plain number (try to guess)
    num_match = re.search(r'([\d,\.]+)', price_str)
    if num_match:
        val = float(num_match.group(1).replace(',', ''))
        if val > 1_000_000_000:
            # Likely VND
            return val / (vnd_per_usd * 1000)
        elif val > 100_000:
            # Likely USD
            return val
        elif val > 1000:
            # Likely thousands USD
            return val * 1000

    return None


def parse_sqm(size_str):
    """Extract square meters from size string."""
    if not size_str:
        return None
    match = re.search(r'([\d\.]+)\s*(sqm|m2|m\u00b2|sq\.?\s*m)', str(size_str).lower())
    if match:
        return float(match.group(1))
    # Just a number
    match2 = re.search(r'(\d+)', str(size_str))
    if match2:
        val = float(match2.group(1))
        if 15 <= val <= 500:  # reasonable sqm range
            return val
    return None


def parse_bedrooms(br_str):
    """Extract number of bedrooms."""
    if not br_str:
        return None
    br_str = str(br_str).lower()
    if 'studio' in br_str:
        return 0
    match = re.search(r'(\d+)\s*(?:br|bed|bedroom|ph\u00f2ng ng\u1ee7|pn)', br_str)
    if match:
        return int(match.group(1))
    match2 = re.search(r'(\d+)', br_str)
    if match2:
        val = int(match2.group(1))
        if 0 <= val <= 10:
            return val
    return None

def detect_sea_proximity(text):
    """Guess sea proximity from listing description."""
    text = str(text).lower()
    if any(w in text for w in ['beachfront', 'beach front', 'bi\u1ec3n', 's\u00e1t bi\u1ec3n', 'm\u1eb7t bi\u1ec3n', 'ocean front', 'sea front']):
        return 'beachfront'
    if any(w in text for w in ['100m', '150m', '200m', 'g\u1ea7n bi\u1ec3n', 'near beach', 'near sea', 'walking distance']):
        return 'under_200m'
    if any(w in text for w in ['300m', '400m', '500m']):
        return 'under_500m'
    if any(w in text for w in ['1km', '800m', '700m']):
        return 'under_1km'
    if any(w in text for w in ['2km', '1.5km']):
        return 'under_2km'
    if any(w in text for w in ['sea view', 'ocean view', 'view bi\u1ec3n', 'h\u01b0\u1edbng bi\u1ec3n']):
        return 'under_500m'
    if any(w in text for w in ['coastal', 'island', '\u0111\u1ea3o']):
        return 'coastal'
    if any(w in text for w in ['mountain', 'highland', 'n\u00fai', 'cao nguy\u00ean']):
        return 'mountain'
    return None


def detect_developer_tier(developer_name, known_developers):
    """Match developer to reputation tier."""
    if not developer_name:
        return 'unknown'
    dev_lower = developer_name.lower()
    for known, tier in known_developers.items():
        if known in dev_lower:
            return tier
    return 'unknown'


def detect_foreign_ownership(text):
    """Score foreign ownership clarity from description."""
    text = str(text).lower()
    if any(w in text for w in ['long-term', 'l\u00e2u d\u00e0i', 'permanent', 'freehold', 's\u1ed5 h\u1ed3ng']):
        return 7
    if any(w in text for w in ['50 year', '50-year', '50 n\u0103m', 'leasehold', 'foreign quota', 's\u1edf h\u1eefu n\u01b0\u1edbc ngo\u00e0i']):
        return 5
    if any(w in text for w in ['condotel', 'timeshare']):
        return 3
    if any(w in text for w in ['foreign', 'n\u01b0\u1edbc ngo\u00e0i', 'expat']):
        return 4
    return 3  # unknown defaults to cautious score


def score_listing(listing, location_key, config):
    """
    Score a single listing on the 1-7 scale.

    listing dict expected keys:
        - price_usd: float or str
        - size_sqm: float or str
        - bedrooms: int or str
        - description: str (full text)
        - developer: str
        - title: str
        - sea_proximity: str (optional override)
        - foreign_ownership: str (optional override)
    """
    weights = config['scoring_weights']
    loc_config = config['locations'].get(location_key, {})

    # Parse values
    price_usd = listing.get('price_usd')
    if isinstance(price_usd, str):
        price_usd = parse_price_usd(price_usd, config.get('vnd_per_usd', 24000))

    size_sqm = listing.get('size_sqm')
    if isinstance(size_sqm, str):
        size_sqm = parse_sqm(size_sqm)

    bedrooms = listing.get('bedrooms')
    if isinstance(bedrooms, str):
        bedrooms = parse_bedrooms(bedrooms)

    full_text = f"{listing.get('title', '')} {listing.get('description', '')} {listing.get('developer', '')}"

    scores = {}

    # 1. Price per sqm (20%)
    if price_usd and size_sqm and size_sqm > 0:
        price_per_sqm = price_usd / size_sqm
        if price_per_sqm < 1500:
            scores['price_per_sqm'] = 7
        elif price_per_sqm < 2000:
            scores['price_per_sqm'] = 6
        elif price_per_sqm < 2500:
            scores['price_per_sqm'] = 5
        elif price_per_sqm < 3000:
            scores['price_per_sqm'] = 4
        elif price_per_sqm < 4000:
            scores['price_per_sqm'] = 3
        elif price_per_sqm < 5000:
            scores['price_per_sqm'] = 2
        else:
            scores['price_per_sqm'] = 1
    elif price_usd:
        if price_usd < 50000:
            scores['price_per_sqm'] = 6
        elif price_usd < 100000:
            scores['price_per_sqm'] = 5
        elif price_usd < 150000:
            scores['price_per_sqm'] = 4
        else:
            scores['price_per_sqm'] = 2
    else:
        scores['price_per_sqm'] = 3  # unknown

    # 2. Location tier (15%)
    scores['location_tier'] = loc_config.get('location_tier', 4)

    # 3. Sea/beach proximity (15%)
    sea_prox = listing.get('sea_proximity') or detect_sea_proximity(full_text) or loc_config.get('sea_proximity_default', 'coastal')
    scores['sea_proximity'] = config['sea_proximity_scores'].get(sea_prox, 3)

    # 4. Growth potential (15%)
    growth_low = loc_config.get('growth_pct_low', 30)
    growth_high = loc_config.get('growth_pct_high', 60)
    avg_growth = (growth_low + growth_high) / 2
    if avg_growth >= 80:
        scores['growth_potential'] = 7
    elif avg_growth >= 60:
        scores['growth_potential'] = 6
    elif avg_growth >= 45:
        scores['growth_potential'] = 5
    elif avg_growth >= 30:
        scores['growth_potential'] = 4
    else:
        scores['growth_potential'] = 3

    # 5. Regional development (10%)
    scores['regional_development'] = loc_config.get('regional_development_score', 4)

    # 6. Air quality (5%)
    air_q = listing.get('air_quality') or loc_config.get('air_quality_default', 'good')
    scores['air_quality'] = config['air_quality_scores'].get(air_q, 4)

    # 7. Developer reputation (10%)
    dev_tier = detect_developer_tier(listing.get('developer', ''), config.get('known_developers', {}))
    scores['developer_reputation'] = config['developer_tiers'].get(dev_tier, 3)

    # 8. Foreign ownership clarity (5%)
    scores['foreign_ownership_clarity'] = detect_foreign_ownership(full_text)

    # 9. Bedroom criteria fit (5%)
    min_br = loc_config.get('min_bedrooms', 1)
    max_br = loc_config.get('max_bedrooms', 99)
    if bedrooms is not None:
        if min_br <= bedrooms <= max_br:
            scores['bedroom_criteria_fit'] = 7
        elif bedrooms == min_br - 1 or bedrooms == max_br + 1:
            scores['bedroom_criteria_fit'] = 4
        else:
            scores['bedroom_criteria_fit'] = 1
    else:
        scores['bedroom_criteria_fit'] = 4  # unknown

    # Budget filter: if over budget, heavy penalty
    budget_max = config.get('budget_max_usd', 150000)
    over_budget = False
    if price_usd and price_usd > budget_max:
        over_budget = True

    # Weighted composite
    composite = sum(scores[k] * weights[k] for k in weights if k in scores)

    # Apply over-budget penalty
    if over_budget:
        composite *= 0.5

    # Round to 1 decimal
    final_score = round(composite, 1)

    return {
        'final_score': final_score,
        'component_scores': scores,
        'parsed': {
            'price_usd': price_usd,
            'size_sqm': size_sqm,
            'bedrooms': bedrooms,
            'sea_proximity': sea_prox,
            'over_budget': over_budget
        }
    }


if __name__ == '__main__':
    # Test with a sample listing
    config = load_config()

    sample = {
        'title': 'Sun Grand City Hillside 1BR Apartment',
        'price_usd': 85000,
        'size_sqm': 38,
        'bedrooms': 1,
        'developer': 'Sun Group',
        'description': 'Beachfront apartment in An Thoi, South Phu Quoc. Long-term ownership. Sea view.',
        'sea_proximity': 'beachfront'
    }

    result = score_listing(sample, 'phu_quoc', config)
    print(f"Score: {result['final_score']}/7")
    print(f"Components: {json.dumps(result['component_scores'], indent=2)}")
    print(f"Parsed: {json.dumps(result['parsed'], indent=2)}")