// Deep-dive on click (Phase 7 slice 3). Vanilla JS, event delegation.
document.addEventListener('DOMContentLoaded', function () {
  document.body.addEventListener('click', async function (e) {
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
