// static/main.js
async function refresh() {
  try {
    const res = await fetch('/metrics', {cache: 'no-store'});
    const data = await res.json();
    const tbody = document.querySelector('#table tbody');
    tbody.innerHTML = '';
    data.holes_mm.forEach((d, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${i + 1}</td><td>${d.toFixed(2)}</td>`;
      tbody.appendChild(tr);
    });
    const meta = document.querySelector('#meta');
    const ts = new Date((data.timestamp || 0) * 1000);
    meta.textContent = `Detected: ${data.count} • Updated: ${isNaN(ts) ? '-' : ts.toLocaleTimeString()}`;
  } catch (e) {
    // ignore transient errors
  } finally {
    setTimeout(refresh, 500);
  }
}
refresh();

// ---- Focus control ----
const focusBtn = document.getElementById('focusBtn');
const lensInput = document.getElementById('lensPos');

if (focusBtn) {
  focusBtn.addEventListener('click', async () => {
    const pos = parseFloat(lensInput.value || '11.5');
    try {
      const res = await fetch(`/focus?pos=${pos}`, { method: 'POST' });
      const data = await res.json();
      alert(data.status === 'ok' ? `Focus set to ${pos}` : `Error: ${data.message}`);
    } catch (e) {
      alert('Focus request failed');
    }
  });
}
