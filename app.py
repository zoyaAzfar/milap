from urllib.parse import quote

from flask import Flask, abort, render_template, request, url_for

import data

app = Flask(__name__)

# {{ facility.type|slug }} -> "special-education-school", used for the
# per-type color classes in the templates and CSS.
app.add_template_filter(data.slugify, "slug")


@app.context_processor
def inject_globals():
    return {
        "needs": data.NEEDS,
        "need_labels": data.NEED_LABELS,
        "total_facility_count": len(data.FACILITIES),
    }


def _map_points(facilities):
    """Marker data for the Leaflet map (see static/js/map.js)."""
    points = data.to_map_points(facilities)
    for p in points:
        p["url"] = url_for("facility_detail", slug=p["slug"])
    return points


@app.route("/")
def index():
    return render_template("index.html", stats=data.home_stats())


@app.route("/browse/")
def browse():
    return render_template(
        "browse.html",
        results=data.FACILITIES,
        options=data.filter_options(),
        filter_data=data.filter_index(),
        age_bands=data.AGE_BAND_LOOKUP,
        map_points=_map_points(data.FACILITIES),
    )


@app.route("/facility/<slug>/")
def facility_detail(slug):
    facility = data.get_facility(slug)
    if facility is None:
        abort(404)
    maps_query = quote(f"{facility['name']}, {facility['address']}")
    maps_url = f"https://www.google.com/maps/search/?api=1&query={maps_query}"
    return render_template("facility.html", f=facility, maps_url=maps_url)


@app.route("/insights/")
def insights():
    return render_template(
        "insights.html",
        stats=data.compute_insights(),
        map_points=_map_points(data.FACILITIES),
        cost_categories=data.COST_CATEGORIES,
        facility_types=data.FACILITY_TYPES,
    )

@app.route("/find-support/")
def qna_finder():
    return render_template(
        "qna.html",
        facilities=data.FACILITIES,
        options=data.filter_options(),
        filter_data=data.filter_index(),
    )

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
