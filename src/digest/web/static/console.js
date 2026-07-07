// Deep-dive on click (Phase 7 slice 3). Vanilla JS, event delegation.
document.addEventListener('DOMContentLoaded', function () {
  document.body.addEventListener('click', async function (e) {
    var pin = e.target.closest('.pin-btn');
    if (pin) {
      var pinned = pin.dataset.pinned === 'true';
      try {
        var r;
        if (pinned) {
          r = await fetch('/pins/' + pin.dataset.key, { method: 'DELETE' });
        } else {
          r = await fetch('/pins', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stamp: pin.dataset.stamp, index: Number(pin.dataset.index) }),
          });
        }
        if (!r.ok) throw new Error('status ' + r.status);
        var data = await r.json();
        pin.dataset.pinned = data.pinned ? 'true' : 'false';
        if (data.key) pin.dataset.key = data.key;
        pin.innerHTML = data.pinned ? '★ saved' : '☆ save';
        pin.classList.toggle('text-amber', data.pinned);
        pin.classList.toggle('text-muted', !data.pinned);
        if (!data.pinned && document.querySelector('[data-page="saved"]')) {
          var card = pin.closest('article');
          if (card) {
            card.classList.add('removing');
            setTimeout(function () {
              card.remove();
              var count = document.getElementById('savedCount');
              var left = document.querySelectorAll('main[data-page="saved"] article').length;
              if (count) count.textContent = 'saved · ' + left;
              var empty = document.getElementById('savedEmpty');
              if (empty && left === 0) empty.hidden = false;
            }, 250);
          }
        }
      } catch (err) {
        var pn = document.createElement('span');
        pn.className = 'deepdive-error';
        pn.textContent = ' pin failed, retry';
        pin.after(pn);
        setTimeout(function () { pn.remove(); }, 4000);
      }
      return;
    }
    var btn = e.target.closest('.deepdive-btn');
    if (!btn) return;
    var slot = btn.closest('.deepdive-slot');
    var url = '/d/' + btn.dataset.stamp + '/deepdive/' + btn.dataset.index;
    var prev = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = 'researching<span class="dots"></span>';
    try {
      var resp = await fetch(url, { method: 'POST' });
      if (!resp.ok) throw new Error('status ' + resp.status);
      slot.innerHTML = await resp.text();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = prev;
      var note = document.createElement('span');
      note.className = 'deepdive-error';
      note.textContent = ' could not deep-dive, retry';
      btn.after(note);
      setTimeout(function () { note.remove(); }, 4000);
    }
  });

  // Live search filter on Saved / Archive.
  var box = document.getElementById('searchBox');
  if (box) {
    var noMatches = document.getElementById('noMatches');
    box.addEventListener('input', function () {
      var q = box.value.trim().toLowerCase();
      var items = document.querySelectorAll('[data-search]');
      var shown = 0;
      items.forEach(function (el) {
        var hit = !q || (el.getAttribute('data-search') || '').indexOf(q) !== -1;
        el.hidden = !hit;
        if (hit) shown++;
      });
      if (noMatches) noMatches.hidden = shown !== 0;
    });
  }
});
