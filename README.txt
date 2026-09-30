Sehat Haq - directory of special-education & disability services in Lahore

RUN IT
  1. pip install -r requirements.txt
  2. python app.py
  3. open http://127.0.0.1:5000

FOLDER LAYOUT
  app.py            Flask routes
  data.py           loads facilities.csv and does all filtering / stats
  facilities.csv    the data (edit this to add or change facilities)
  templates/        HTML pages (_map.html is the shared map block)
  static/css/       style.css
  static/js/        map.js (Leaflet map)

NOTES
  - A blank cell in facilities.csv means "not available": that row simply
    isn't shown on the site.
  - The CSV can be saved as UTF-8 or Mac Roman; data.py handles both.
  - Maps and fonts load from the internet (OpenStreetMap, unpkg, Google Fonts).
