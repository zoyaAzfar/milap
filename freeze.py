from flask import render_template
from flask_frozen import Freezer
from app import app
import data

app.config["FREEZER_DESTINATION"] = "build"
freezer = Freezer(app)

@freezer.register_generator
def facility_detail():
    for f in data.FACILITIES:
        yield {"slug": f["slug"]}

if __name__ == "__main__":
    freezer.freeze()
    # Frozen-Flask doesn't generate error pages, so write the 404 by hand
    with app.test_request_context():
        html = render_template("404.html")
    with open("build/404.html", "w", encoding="utf-8") as fh:
        fh.write(html)