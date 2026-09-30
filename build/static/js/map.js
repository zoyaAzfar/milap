// Shared Leaflet map for /browse and /insights.
//
// Expects, on the page:
//   <div data-facility-map> ...................... where the map is drawn
//   <script type="application/json" id="map-points"> ... [{name, lat, lon, url,
//                                                            type, type_key, ownership}]
//
// Pin colors come from CSS (.pin.type-<type_key>), so all colors live in
// style.css. Popup content is built with textContent, never innerHTML.
(function () {
  var el = document.querySelector('[data-facility-map]');
  var dataEl = document.getElementById('map-points');
  if (!el || !dataEl || typeof L === 'undefined') return;

  var points = [];
  try {
    points = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }

  var map = L.map(el, { scrollWheelZoom: false }).setView([31.5204, 74.3587], 11);

  // Don't hijack page scrolling: wheel-zoom only after the map has focus.
  map.on('focus', function () { map.scrollWheelZoom.enable(); });
  map.on('blur', function () { map.scrollWheelZoom.disable(); });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
  }).addTo(map);

  function popupFor(p) {
    var box = document.createElement('div');
    box.className = 'pin-popup';

    var name = document.createElement('strong');
    name.textContent = p.name;
    box.appendChild(name);

    var kind = document.createElement('span');
    kind.textContent = p.type + ', ' + p.ownership;
    box.appendChild(kind);

    var link = document.createElement('a');
    link.href = p.url;
    link.textContent = 'View profile';
    box.appendChild(link);

    return box;
  }

    var markers = {};
  var bounds = [];
  points.forEach(function (p) {
    var icon = L.divIcon({
      className: 'pin-wrap',
      html: '<span class="pin type-' + p.type_key + '"></span>',
      iconSize: [30, 30],
      iconAnchor: [15, 15],
      popupAnchor: [0, -14]
    });
    markers[p.slug] = L.marker([p.lat, p.lon], { icon: icon, title: p.name, keyboard: true })
      .addTo(map)
      .bindPopup(popupFor(p));
    bounds.push([p.lat, p.lon]);
  });

  function fit(latlngs) {
    if (latlngs.length) map.fitBounds(latlngs, { padding: [30, 30], maxZoom: 15 });
  }
  fit(bounds);

  // browse.js announces which facilities pass the current filters.
  document.addEventListener('facilities:filtered', function (e) {
    var keep = new Set(e.detail.slugs), shown = [];
    Object.keys(markers).forEach(function (slug) {
      var m = markers[slug];
      if (keep.has(slug)) {
        if (!map.hasLayer(m)) m.addTo(map);
        shown.push(m.getLatLng());
      } else if (map.hasLayer(m)) {
        map.removeLayer(m);
      }
    });
    fit(shown);
  });
})();