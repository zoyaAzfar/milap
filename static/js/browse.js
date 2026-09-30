(function () {
  var data = JSON.parse(document.getElementById('filter-data').textContent);
  var ageBands = JSON.parse(document.getElementById('age-bands').textContent);
  var panel = document.getElementById('filters');
  var form = panel.querySelector('form');
  var cards = Array.from(document.querySelectorAll('.facility-card[data-slug]'));
  var countEl = document.getElementById('results-count');
  var emptyEl = document.getElementById('empty-state');
  var badge = document.getElementById('filter-count');

  var MULTI = ['need', 'type', 'ownership', 'cost'];
  var SINGLE = ['q', 'area', 'service', 'level', 'age'];
  var FLAGS = ['wheelchair', 'psl'];

  function readForm() {
    var fd = new FormData(form), s = {};
    MULTI.forEach(function (k) { s[k] = fd.getAll(k); });
    SINGLE.forEach(function (k) { s[k] = (fd.get(k) || '').trim(); });
    FLAGS.forEach(function (k) { s[k] = !!fd.get(k); });
    return s;
  }

  function matches(f, s) {
    var q = s.q.toLowerCase();
    if (q && f.name.indexOf(q) === -1 && f.area.toLowerCase().indexOf(q) === -1) return false;
    if (s.need.length && !s.need.some(function (n) { return f.needs.includes(n); })) return false;
    if (s.area && f.area !== s.area) return false;
    if (s.ownership.length && !s.ownership.includes(f.ownership)) return false;
    if (s.cost.length && !s.cost.includes(f.cost)) return false;
    if (s.type.length && !s.type.includes(f.type)) return false;
    if (s.service && !f.services.includes(s.service)) return false;
    if (s.level && !f.levels.includes(s.level)) return false;
    var band = ageBands[s.age];
    if (s.age && band && !f.ages.some(function (r) { return r[0] <= band[1] && r[1] >= band[0]; })) return false;
    if (s.wheelchair && !f.wheelchair) return false;
    if (s.psl && !f.psl) return false;
    return true;
  }

  function toParams(s) {
    var p = new URLSearchParams();
    MULTI.forEach(function (k) { s[k].forEach(function (v) { p.append(k, v); }); });
    SINGLE.forEach(function (k) { if (s[k]) p.set(k, s[k]); });
    FLAGS.forEach(function (k) { if (s[k]) p.set(k, '1'); });
    return p;
  }

  function apply() {
    var s = readForm(), visible = [];
    cards.forEach(function (card) {
      var ok = matches(data[card.dataset.slug], s);
      card.hidden = !ok;
      if (ok) visible.push(card.dataset.slug);
    });
    var n = visible.length;
    countEl.textContent = n + (n === 1 ? ' facility found' : ' facilities found');
    countEl.hidden = n === 0;
    emptyEl.hidden = n > 0;

    var p = toParams(s);
    var active = new Set(p.keys()).size;
    badge.textContent = active;
    badge.hidden = !active;
    history.replaceState(null, '', active ? '?' + p.toString() : location.pathname);

    document.dispatchEvent(new CustomEvent('facilities:filtered', { detail: { slugs: visible } }));
  }

  function restore() {
    var p = new URLSearchParams(location.search);
    Array.from(form.elements).forEach(function (el) {
      if (!el.name) return;
      var vals = p.getAll(el.name);
      if (el.type === 'checkbox') el.checked = vals.includes(el.value);
      else el.value = vals[0] || '';
    });
  }

  function clearAll(e) {
    e.preventDefault();
    form.reset();
    apply();
  }

  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
  form.querySelector('.btn-outline').addEventListener('click', clearAll);
  document.getElementById('clear-empty').addEventListener('click', clearAll);

  restore();
  apply();
  if (!badge.hidden) panel.open = true;
})();