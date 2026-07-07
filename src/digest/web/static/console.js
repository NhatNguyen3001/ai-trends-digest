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
    btn.textContent = 'researching...';
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
});
