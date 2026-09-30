# -----------------------------------------------------------------------------
# data.py
#
# Loads and models facility data for Sehat Haq from facilities.csv — a
# real audit of special-education / disability services in Lahore (Type,
# location, ownership, disabilities served, services, cost, admissions,
# accessibility, contact details). This module turns each CSV row into a
# facility dict the templates can use, plus a few taxonomies (needs,
# ownership, cost, age bands) and a compute_insights() function that powers
# the /insights page.
# -----------------------------------------------------------------------------

import csv
import os
import re
from collections import Counter
from math import radians, sin, cos, sqrt, atan2
from statistics import mean

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facilities.csv")

# Rough geographic center of Lahore, used only for "distance from center"
# stats on the insights page.
LAHORE_CENTER = (31.5204, 74.3587)

# -----------------------------------------------------------------------------
# Taxonomies
# -----------------------------------------------------------------------------

# The 9 broad need/support categories used on the homepage, filters, and tags.
# Each is (key, label, icon-name); icon-name matches an <svg> symbol defined
# once in base.html and reused everywhere with <svg><use href="#icon-...">.
NEEDS = [
    ("autism", "Autism", "puzzle"),
    ("hearing", "Hearing / Deaf", "ear"),
    ("vision", "Vision", "eye"),
    ("speech", "Speech & Language", "speech"),
    ("learning", "Learning", "book"),
    ("developmental", "Developmental & Intellectual", "sprout"),
    ("physical", "Physical / Motor", "access"),
    ("behavioral", "Behavioral & Mental Health", "heart"),
    ("other", "Other / General", "dots"),
]
NEED_LABELS = {key: label for key, label, _ in NEEDS}
NEED_ICONS = {key: icon for key, _, icon in NEEDS}

# Maps every exact "Disabilities" value found in facilities.csv to one of the
# 9 buckets above. Anything unrecognized falls back to "other" (see
# DISABILITY_BUCKETS.get(...) below) rather than raising, so a future CSV
# update with a new term doesn't break the site — it just lands in "Other".
DISABILITY_BUCKETS = {
    "Autism Spectrum Disorder (ASD)": "autism",
    "Intellectually/Mentally Challenged (IC/MC)": "developmental",
    "Hearing Impairment (HI)": "hearing",
    "Visual Impairment (VI)": "vision",
    "Speech & Language Difficulty": "speech",
    "Physically Disabled (PD)": "physical",
    "Down Syndrome": "developmental",
    "Slow Learners (SL)": "learning",
    "Learning Challenges": "learning",
    "Learning Challenges / Slow Learners (SL)": "learning",
    "Developmental Disorders": "developmental",
    "Cerebral Palsy (CP)": "physical",
    "Developmental Delay": "developmental",
    "ADHD": "behavioral",
    "All Disabilities (Inclusive)": "other",
    "Depression": "behavioral",
    "OCD": "behavioral",
    "ODD": "behavioral",
    "PTSD": "behavioral",
    "Motor Skill Weakness": "physical",
    "Sensory Processing Needs": "behavioral",
    "Behavioural Disorders": "behavioral",
    "Special Needs (General)": "other",
}

# facilities.csv's "Sector" column is Public / Private / Private NGO — this is
# who runs the place, not a geographic sector. Mapped onto the site's existing
# ownership vocabulary.
OWNERSHIP_MAP = {"Public": "Government", "Private": "Private", "Private NGO": "Nonprofit"}
OWNERSHIPS = ["Government", "Private", "Nonprofit"]

# Derived from the "Price" column (see _cost_category). "Not Published" is
# kept as its own bucket rather than folded into "Paid" because whether a fee
# is disclosed at all is one of the things the insights page reports on.
COST_CATEGORIES = ["Free", "Subsidized", "Paid", "Not Published"]

AGE_BANDS = [
    ("0-3", "0–3 years", 0, 3),
    ("3-5", "3–5 years", 3, 5),
    ("6-12", "6–12 years", 6, 12),
    ("13-18", "13–18 years", 13, 18),
    ("18+", "18 years and up", 18, 200),
]
AGE_BAND_LOOKUP = {key: (lo, hi) for key, _, lo, hi in AGE_BANDS}

# Used only to write a plain-language sentence in _build_description.
TYPE_PHRASES = {
    "Special Education School": "special-education school",
    "Therapy": "therapy center",
    "Vocational Training": "vocational training center",
}


# -----------------------------------------------------------------------------
# Small parsing helpers — each handles one messy real-world CSV column.
# -----------------------------------------------------------------------------

def _slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text or "facility"


slugify = _slugify  # public name used by app.py / templates


def _split_list(raw):
    """Split a comma-separated CSV cell into clean items.

    One service name in the source data — "Music, Art & Craft Therapy" —
    itself contains a comma, so a naive split breaks it into two fake
    services ("Music" and "Art & Craft Therapy"). This re-merges that one
    case; every other cell is a plain comma-separated list.
    """
    items = [p.strip() for p in raw.split(",") if p.strip()]
    fixed = []
    i = 0
    while i < len(items):
        if items[i] == "Music" and i + 1 < len(items) and items[i + 1] == "Art & Craft Therapy":
            fixed.append("Music, Art & Craft Therapy")
            i += 2
        else:
            fixed.append(items[i])
            i += 1
    return fixed


def _parse_age(raw):
    """Returns (age_min, age_max, display_label) from a free-text age column
    like '3-12 years', '2+ years', 'All Ages', or ''. A blank cell means the
    age isn't available, so it returns (None, None, None) and nothing is shown."""
    raw = (raw or "").strip()
    if not raw:
        return None, None, None
    if re.search(r"all\s*ages", raw, re.I):
        return 0.0, 200.0, raw
    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", raw)
    if m:
        return float(m.group(1)), float(m.group(2)), raw
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", raw)
    if m:
        return float(m.group(1)), 200.0, raw
    return 0.0, 200.0, raw


def _parse_age_ranges(raw):
    """All (lo, hi) ranges in an age cell, e.g. '2-3 years (...), 12-16 years (...)'
    gives [(2, 3), (12, 16)]. 'All Ages' / unparseable -> [(0, 200)].
    Blank -> [] (age not available, so it won't match an age filter)."""
    raw = (raw or "").strip()
    if not raw:
        return []
    if re.search(r"all\s*ages", raw, re.I):
        return [(0.0, 200.0)]
    ranges = [(float(a), float(b)) for a, b in
              re.findall(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", raw)]
    ranges += [(float(a), 200.0) for a in re.findall(r"(\d+(?:\.\d+)?)\s*\+", raw)]
    return ranges or [(0.0, 200.0)]


def _clean_phones(raw):
    """One Contact cell can hold several numbers ('+92 42 111, +92 42 222').
    Returns [{'display': ..., 'href': ...}, ...] for the template's tel: links."""
    phones = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        href = re.sub(r"[^\d+]", "", part)
        if href:
            phones.append({"display": part, "href": href})
    return phones


_DAY_START = re.compile(r",\s*(?=(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b)")


def _hours_lines(raw):
    """Split 'Mon-Thu 9-1, Fri 9-12 (Sat-Sun Closed)' into one line per day-group.
    Splits only where the next chunk starts with a day, so split shifts like
    'Mon-Fri 9:00 AM-12:45 PM, 1:00 PM-4:00 PM' stay on one line."""
    raw = (raw or "").strip()
    return [p.strip() for p in _DAY_START.split(raw) if p.strip()] if raw else []


def _cost_label(price_raw, category):
    """Short label for the browse cards."""
    if category == "Paid":
        return price_raw
    return {"Free": "Free", "Subsidized": "Subsidized fee",
            "Not Published": "Fee not published"}[category]


def _clean_phone(raw):
    """Returns (display_text, tel_href). Some Contact cells carry more than
    one number or a trailing note in parentheses; the href needs just the
    first phone-looking run of digits, the display keeps the full text."""
    raw = (raw or "").strip()
    m = re.match(r"^([+\d][\d\s\-]{6,}\d)", raw)
    snippet = m.group(1) if m else raw
    href = re.sub(r"[^\d+]", "", snippet)
    return raw, href


def _tri_state(raw):
    raw = (raw or "").strip().lower()
    if raw == "yes":
        return True
    if raw == "no":
        return False
    return None  # "Unknown" or blank


def _cost_category(price_raw):
    price_raw = (price_raw or "").strip()
    if price_raw == "Free":
        return "Free"
    if price_raw.startswith("Subsidized"):
        return "Subsidized"
    if not price_raw or price_raw == "Not Published":
        return "Not Published"
    return "Paid"


def _fee_note(price_raw, category):
    price_raw = (price_raw or "").replace("\xa0", " ").strip()
    if category == "Free":
        return "No fee reported."
    if category == "Not Published":
        return "Fee not published by the facility — contact them directly for pricing."
    if category == "Subsidized":
        return "Subsidized fee — contact the facility for the exact amount."
    return f"Reported fee: {price_raw}."


# Best-effort neighborhood extraction from free-text addresses. facilities.csv
# has no separate "area" column, only a full address plus precise lat/lon —
# the map uses the real coordinates; this label is only an approximation used
# for grouping and the area filter/stat.
_AREA_KEYWORDS = [
    ("Twp", "Township"),
    ("Township", "Township"),
    ("Bankers Cooperative", "Bankers Cooperative Housing Society"),
    ("Wapda Town", "Wapda Town"),
    ("Makkah Colony", "Makkah Colony"),
    ("U.E.T.", "UET Housing Society"),
    ("UET Housing", "UET Housing Society"),
    ("Engineers Town", "Engineers Town"),
    ("Punjab University", "Punjab University Area"),
    ("Aitchison", "Aitchison Society"),
    ("Jinnah Town", "Jinnah Town"),
    ("Johar Town", "Johar Town"),
    ("Super Town", "Super Town"),
    ("Model Town", "Model Town"),
    ("Faisal Town", "Faisal Town"),
    ("Bahria Town", "Bahria Town"),
    ("Jati Umrah", "Jati Umrah"),
    ("Mughalpura", "Mughalpura"),
    ("Walton", "Walton"),
    ("Zaitoon", "Zaitoon"),
    ("Allama Iqbal Town", "Allama Iqbal Town"),
    ("Iqbal Town", "Allama Iqbal Town"),
    ("Chauburji", "Chauburji"),
    ("Shalimar Town", "Shalimar Town"),
    ("Aziz Bhatti", "Aziz Bhatti Town"),
    ("Samanabad", "Samanabad"),
    ("Sheranwala", "Walled City"),
    ("Walled City", "Walled City"),
    ("Ravi Road", "Ravi Road"),
    ("Raiwind", "Raiwind"),
    ("Thokar Niaz Baig", "Thokar Niaz Baig"),
    ("Abpara Housing", "Thokar Niaz Baig"),
    ("Gujjar Pura", "Gujjar Pura"),
    ("Wagha Town", "Wagha Town"),
    ("Wahga Town", "Wagha Town"),
    ("Architects Engineers Housing", "Architects Engineers Housing Society"),
    ("Cantt", "Cantt"),
]


def _extract_area(address):
    m = re.search(r"D\.?H\.?A\.?[^,]*?Phase\s*(\d+)", address, re.I)
    if m:
        return f"DHA Phase {m.group(1)}"
    if re.search(r"D\.?H\.?A\.?", address, re.I):
        return "DHA"

    # Gulberg I/II/III are adjacent, so they're grouped as one neighborhood.
    # (DHA phases, by contrast, are large and far apart, so they stay separate.)
    if re.search(r"Gulberg", address, re.I):
        return "Gulberg"

    low = address.lower()
    for kw, label in _AREA_KEYWORDS:
        if kw.lower() in low:
            return label
    return "Other Lahore"


def _join_list(items, n=3):
    if not items:
        return ""
    shown = items[:n]
    if len(shown) == 1:
        text = shown[0]
    elif len(shown) == 2:
        text = f"{shown[0]} and {shown[1]}"
    else:
        text = ", ".join(shown[:-1]) + f", and {shown[-1]}"
    if len(items) > n:
        text += ", among others"
    return text


def _build_description(type_raw, ownership, area, services, disabilities):
    type_phrase = TYPE_PHRASES.get(type_raw, "facility")
    svc = _join_list(services, 3)
    if svc:
        return f"A {type_phrase} providing {svc}."
    return f"A {type_phrase}."


# -----------------------------------------------------------------------------
# Loading facilities.csv
# -----------------------------------------------------------------------------

def _load_facilities():
    facilities = []
    seen_slugs = {}

    # The CSV was saved from a Mac app as Mac Roman, not UTF-8. Try UTF-8 first
    # (what a database export will normally be) and fall back to Mac Roman.
    with open(CSV_PATH, "rb") as fh:
        raw_bytes = fh.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("mac_roman")

    reader = csv.DictReader(text.splitlines(keepends=True))
    for row in reader:
        name = row["Name"].strip()

        base_slug = _slugify(name)
        count = seen_slugs.get(base_slug, 0)
        seen_slugs[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"

        type_raw = row["Type"].strip()
        ownership = OWNERSHIP_MAP.get(row["Sector"].strip(), row["Sector"].strip())
        address = row["Address"].strip()
        area = _extract_area(address)

        try:
            lat = float(row["lat"]) if row["lat"].strip() else None
            lon = float(row["lon"]) if row["lon"].strip() else None
        except ValueError:
            lat = lon = None

        disabilities = _split_list(row["Disabilities"])
        services = _split_list(row["Services"])
        amenities = _split_list(row["Facilities"])
        levels = _split_list(row["Level Of School"])
        languages = [
            "Pakistan Sign Language (PSL)" if l == "PSL" else l
            for l in _split_list(row["Medium of Instruction"])
        ]
        needs = sorted({DISABILITY_BUCKETS.get(d, "other") for d in disabilities})

        age_min, age_max, age_label = _parse_age(row["Age Group"])

        price_raw = row["Price"].replace("\xa0", " ").strip()
        cost_category = _cost_category(price_raw)
        fee_note = _fee_note(price_raw, cost_category)

        phone_display, phone_href = _clean_phone(row["Contact"])

        psl_available = (
            any("sign language" in s.lower() for s in services)
            or "PSL" in row["Medium of Instruction"]
        )

        facilities.append({
            "slug": slug,
            "name": name,
            "type": type_raw,
            "ownership": ownership,
            "needs": needs,
            "disabilities": disabilities,
            "area": area,
            "address": address,
            "lat": lat,
            "lon": lon,
            "age_min": age_min,
            "age_max": age_max,
            "age_label": age_label,
            "age_ranges": _parse_age_ranges(row["Age Group"]),
            "gender": row["Gender"].strip() or None,
            "admission_status": row["Admission"].strip() or None,
            "services": services,
            "amenities": amenities,
            "levels": levels,
            "languages": languages,
            "description": _build_description(type_raw, ownership, area, services, disabilities),
            "cost_category": cost_category,
            "price_raw": price_raw,
            "fee_note": fee_note,
            "cost_label": _cost_label(price_raw, cost_category),
            "phone": phone_display,
            "phone_href": phone_href,
            "phones": _clean_phones(row["Contact"]),
            "hours": row["Hours"].strip(),
            "hours_lines": _hours_lines(row["Hours"]),
            "transport": _tri_state(row["Transport"]),
            "live_in": row["Live-in Facility"].strip().lower() == "yes",
            "wheelchair_accessible": _tri_state(row["Wheelchair Accessibility"]),
            "psl_available": psl_available,
            "website": row["Website / Social Media"].strip() or None,
            "email": None,
            "source": row["Source"].strip() or None,
        })

    return facilities


FACILITIES = _load_facilities()
FACILITY_TYPES = sorted({f["type"] for f in FACILITIES})


# -----------------------------------------------------------------------------
# Public helpers used by app.py / templates
# -----------------------------------------------------------------------------

def all_areas():
    return sorted({f["area"] for f in FACILITIES})


def all_services():
    services = set()
    for f in FACILITIES:
        services.update(f["services"])
    return sorted(services)


def all_levels():
    levels = set()
    for f in FACILITIES:
        levels.update(f["levels"])
    return sorted(levels)


def home_stats():
    """Numbers for the homepage stat strip."""
    return {
        "total": len(FACILITIES),
        "areas": len({f["area"] for f in FACILITIES}),
        "free_or_subsidized": sum(
            1 for f in FACILITIES if f["cost_category"] in ("Free", "Subsidized")
        ),
        "psl": sum(1 for f in FACILITIES if f["psl_available"]),
    }


def filter_options():
    """Choices for the browse filter form."""
    return {
        "needs": NEEDS,
        "types": FACILITY_TYPES,
        "services": all_services(),
        "areas": all_areas(),
        "age_bands": AGE_BANDS,
        "levels": all_levels(),
        "ownerships": OWNERSHIPS,
        "cost_categories": COST_CATEGORIES,
    }


_FILTER_KEYS = ("q", "need", "type", "area", "ownership", "cost",
                "service", "level", "age", "wheelchair", "psl")


def active_filter_count(args):
    """How many filters are set (shown as the badge on the Filters button)."""
    return sum(1 for k in _FILTER_KEYS if any(v.strip() for v in args.getlist(k)))


def get_facility(slug):
    for f in FACILITIES:
        if f["slug"] == slug:
            return f
    return None


def _age_overlaps(f, band_key):
    if band_key not in AGE_BAND_LOOKUP:
        return True
    lo, hi = AGE_BAND_LOOKUP[band_key]
    return any(a <= hi and b >= lo for a, b in f["age_ranges"])


def filter_facilities(args):
    """args is a werkzeug MultiDict (request.args)."""
    results = list(FACILITIES)

    q = (args.get("q") or "").strip().lower()
    if q:
        results = [f for f in results if q in f["name"].lower() or q in f["area"].lower()]

    needs = args.getlist("need")
    if needs:
        results = [f for f in results if any(n in f["needs"] for n in needs)]

    area = args.get("area") or ""
    if area:
        results = [f for f in results if f["area"] == area]

    ownership = args.getlist("ownership")
    if ownership:
        results = [f for f in results if f["ownership"] in ownership]

    cost = args.getlist("cost")
    if cost:
        results = [f for f in results if f["cost_category"] in cost]

    ftype = args.getlist("type")
    if ftype:
        results = [f for f in results if f["type"] in ftype]

    service = args.get("service") or ""
    if service:
        results = [f for f in results if service in f["services"]]

    level = args.get("level") or ""
    if level:
        results = [f for f in results if level in f["levels"]]

    age_band = args.get("age") or ""
    if age_band:
        results = [f for f in results if _age_overlaps(f, age_band)]

    if args.get("wheelchair"):
        results = [f for f in results if f["wheelchair_accessible"]]

    if args.get("psl"):
        results = [f for f in results if f["psl_available"]]

    return results

def filter_index():
    """Per-facility fields the browser filters/ranks on (see static/js/browse.js)."""
    return {
        f["slug"]: {
            "title": f["name"],
            "name": f["name"].lower(),
            "area": f["area"],
            "needs": f["needs"],
            "type": f["type"],
            "ownership": f["ownership"],
            "cost": f["cost_category"],
            "services": f["services"],
            "levels": f["levels"],
            "ages": f["age_ranges"],
            "wheelchair": bool(f["wheelchair_accessible"]),
            "psl": f["psl_available"],
        }
        for f in FACILITIES
    }


def to_map_points(facilities):
    """Minimal per-facility data for the Leaflet map — only what a marker
    popup needs, and only for facilities we can actually place on a map."""
    points = []
    for f in facilities:
        if f["lat"] is None or f["lon"] is None:
            continue
        points.append({
            "slug": f["slug"],
            "name": f["name"],
            "lat": f["lat"],
            "lon": f["lon"],
            "type": f["type"],
            "type_key": slugify(f["type"]),
            "ownership": f["ownership"],
        })
    return points


# -----------------------------------------------------------------------------
# Insights — the computed analysis behind /insights
# -----------------------------------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def compute_insights():
    facs = FACILITIES
    total = len(facs)
    geocoded = [f for f in facs if f["lat"] is not None and f["lon"] is not None]

    # --- Geography: where services cluster, and how far a family might travel ---
    area_counts = Counter(f["area"] for f in facs)
    top_areas = area_counts.most_common(6)
    single_areas = sorted(a for a, c in area_counts.items() if c == 1)

    dists_center = [
        (f["name"], _haversine_km(LAHORE_CENTER[0], LAHORE_CENTER[1], f["lat"], f["lon"]))
        for f in geocoded
    ]
    dist_values = [d for _, d in dists_center]

    nn_dists = []
    isolated = []  # facilities with no other listed facility within 3 km
    for i, f in enumerate(geocoded):
        others = [
            _haversine_km(f["lat"], f["lon"], g["lat"], g["lon"])
            for j, g in enumerate(geocoded) if j != i
        ]
        if others:
            nearest = min(others)
            nn_dists.append(nearest)
            if nearest > 3:
                isolated.append((f["name"].rstrip("."), nearest))
    isolated.sort(key=lambda x: -x[1])

    farthest_name, farthest_km = max(dists_center, key=lambda x: x[1]) if dists_center else (None, 0)

    geography = {
        "geocoded": len(geocoded),
        "total": total,
        "area_count": len(area_counts),
        "top_areas": top_areas,
        "single_areas": single_areas,
        "avg_dist_center_km": mean(dist_values) if dist_values else 0,
        "within_5km_pct": (sum(1 for d in dist_values if d <= 5) / len(dist_values) * 100) if dist_values else 0,
        "beyond_10km_pct": (sum(1 for d in dist_values if d > 10) / len(dist_values) * 100) if dist_values else 0,
        "avg_nearest_neighbor_km": mean(nn_dists) if nn_dists else 0,
        "max_nearest_neighbor_km": max(nn_dists) if nn_dists else 0,
        "isolated_count": len(isolated),
        "isolated_top": isolated[:4],
        "farthest_name": farthest_name,
        "farthest_km": farthest_km,
    }

    # --- Cost: how many are free / subsidized / paid / undisclosed ---
    cost_counts = Counter(f["cost_category"] for f in facs)
    cost_pct = {k: (v / total * 100) for k, v in cost_counts.items()}

    # --- Services: which are common, which are scarce ---
    service_counts = Counter()
    for f in facs:
        service_counts.update(f["services"])
    common_services = service_counts.most_common(8)
    scarce_services = sorted(
        [(s, c) for s, c in service_counts.items() if c <= 2],
        key=lambda x: (x[1], x[0]),
    )

    # --- Disability: which populations are well served vs. underserved ---
    disability_counts = Counter()
    for f in facs:
        disability_counts.update(f["disabilities"])
    disability_sorted = disability_counts.most_common()
    best_served = disability_sorted[:5]
    # Catch-all labels ("Special Needs (General)", "All Disabilities (Inclusive)")
    # aren't a specific population, so they're left out of the "least served" list.
    generic_labels = {"Special Needs (General)", "All Disabilities (Inclusive)"}
    underserved = sorted(
        [(d, c) for d, c in disability_counts.items() if d not in generic_labels],
        key=lambda x: (x[1], x[0]),
    )[:6]

    # --- Information: how easy is it to tell what a place does & how to reach it ---
    with_phone = sum(1 for f in facs if f["phone"])
    with_website = sum(1 for f in facs if f["website"])
    with_hours = sum(1 for f in facs if f["hours"])
    price_published = sum(1 for f in facs if f["cost_category"] != "Not Published")
    fee_amount_published = sum(1 for f in facs if f["cost_category"] == "Paid")
    mappable = len(geocoded)

    information = {
        "phone_pct": with_phone / total * 100,
        "website_pct": with_website / total * 100,
        "hours_pct": with_hours / total * 100,
        "price_published_pct": price_published / total * 100,
        "fee_amount_pct": fee_amount_published / total * 100,
        "fee_amount_count": fee_amount_published,
        "mappable_pct": mappable / total * 100,
        "not_published_count": total - price_published,
    }

    return {
        "total": total,
        "geography": geography,
        "cost_counts": cost_counts,
        "cost_pct": cost_pct,
        "services": {
            "common": common_services,
            "scarce": scarce_services,
            "distinct": len(service_counts),
        },
        "disability": {
            "counts": disability_sorted,
            "best_served": best_served,
            "underserved": underserved,
            "distinct": len(disability_counts),
        },
        "information": information,
    }

def rank_facilities_by_fit(age=None, need=None, cost_pref=None, area=None, ftype=None):
    """Scores and ranks facilities based on QnA answers."""
    results = []
    
    for f in FACILITIES:
        score = 0
        
        # 1. Age (High Weight: +5 points). Hard constraint.
        if age and age.strip():
            try:
                age_float = float(age)
                if any(lo <= age_float <= hi for lo, hi in f["age_ranges"]):
                    score += 5
                else:
                    continue # Skip entirely if the facility does not serve this age
            except ValueError:
                pass
                
        # 2. Support Need (Medium Weight: +3 points)
        if need and need in f["needs"]:
            score += 3
            
        # 3. Cost Preference (Lower Weight: +2 points)
        if cost_pref:
            if f["cost_category"] == cost_pref:
                score += 2
            elif cost_pref == "Free" and f["cost_category"] == "Subsidized":
                score += 1 # Partial match for budget constraints
                
        # 4. Location / Area (+3 points)
        if area and f["area"] == area:
            score += 3
            
        # 5. Preferred Facility Type (+2 points)
        if ftype and f["type"] == ftype:
            score += 2
                
        # Only include facilities that met at least one criteria
        if score > 0:
            results.append((score, f))
            
    # Sort descending by score, then alphabetically by name
    results.sort(key=lambda x: (-x[0], x[1]["name"]))
    
    return [{"match_score": score, "facility": f} for score, f in results]