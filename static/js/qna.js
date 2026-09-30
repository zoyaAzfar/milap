(function () {
  var data = JSON.parse(document.getElementById('filter-data').textContent);
  var formPanel = document.getElementById('qna-form-panel');
  var form = document.getElementById('qna-form');
  var results = document.getElementById('qna-results');
  var list = document.getElementById('qna-list');
  var emptyEl = document.getElementById('qna-empty');
  var cards = Array.from(list.querySelectorAll('.facility-card[data-slug]'));
  var KEYS = ['age', 'need', 'area', 'type', 'cost'];

  // Same scoring as rank_facilities_by_fit in data.py
  function score(f, a) {
    var s = 0;
    if (a.age) {
      var n = Number(a.age);
      if (!isNaN(n)) {
        if (f.ages.some(function (r) { return r[0] <= n && n <= r[1]; })) s += 5;
        else return null;                       // hard constraint
      }
    }
    if (a.need && f.needs.includes(a.need)) s += 3;
    if (a.cost) {
      if (f.cost === a.cost) s += 2;
      else if (a.cost === 'Free' && f.cost === 'Subsidized') s += 1;
    }
    if (a.area && f.area === a.area) s += 3;
    if (a.type && f.type === a.type) s += 2;
    return s > 0 ? s : null;
  }

  function tier(s) { return s >= 8 ? 'excellent' : s >= 5 ? 'good' : 'fair'; }

  function showResults(a) {
    var scored = [];
    cards.forEach(function (card) {
      var f = data[card.dataset.slug];
      var s = score(f, a);
      card.hidden = s === null;
      if (s !== null) scored.push({ card: card, score: s, title: f.title });
    });
    scored.sort(function (x, y) {
      return y.score - x.score || x.title.localeCompare(y.title);
    });
    scored.forEach(function (item) {
      list.appendChild(item.card);              // moves the card into ranked order
      var t = tier(item.score);
      item.card.querySelectorAll('[data-tier]').forEach(function (b) {
        b.hidden = b.dataset.tier !== t;
      });
    });
    emptyEl.hidden = scored.length > 0;
    formPanel.hidden = true;
    results.hidden = false;
  }

  function showForm() {
    results.hidden = true;
    formPanel.hidden = false;
  }

  function init() {
    var p = new URLSearchParams(location.search), a = {}, any = false;
    KEYS.forEach(function (k) {
      a[k] = (p.get(k) || '').trim();
      form.elements[k].value = a[k];
      if (a[k]) any = true;
    });
    if (any) showResults(a); else showForm();
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(form), p = new URLSearchParams();
    KEYS.forEach(function (k) {
      var v = (fd.get(k) || '').trim();
      if (v) p.set(k, v);
    });
    if (!p.toString()) return;                  // nothing answered: stay on the form
    history.pushState(null, '', '?' + p.toString());
    init();
  });

  function startOver(e) {
    e.preventDefault();
    form.reset();
    history.pushState(null, '', location.pathname);
    showForm();
  }
  document.getElementById('qna-restart').addEventListener('click', startOver);
  document.getElementById('qna-retry').addEventListener('click', startOver);

  window.addEventListener('popstate', init);
  init();
})();