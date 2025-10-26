// ======== Variables ========
let paused = false;
const streamImg = document.getElementById('stream');
const snapBtn = document.getElementById('snapBtn');
const resetBtn = document.getElementById('resetBtn');
const focusBtn = document.getElementById('focusBtn');
const lensInput = document.getElementById('lensPos');
const tableBody = document.querySelector('#table tbody');
const meta = document.getElementById('meta');

// ======== Live Feed Refresh ========
async function refresh() {
  try {
    if (!paused && !streamImg.src.endsWith("/video")) {
      streamImg.src = '/video';
    }

    if (!paused) {
      // Fetch live measurements
      const res = await fetch('/metrics', { cache: 'no-store' });
      const data = await res.json();

      // Update measurements table
      tableBody.innerHTML = '';
      data.holes_mm.forEach((d, i) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${i + 1}</td><td>${d.toFixed(2)}</td>`;
        tableBody.appendChild(tr);
      });

      // Update meta info
      const ts = new Date((data.timestamp || 0) * 1000);
      meta.textContent = `Detected: ${data.count} • Updated: ${isNaN(ts) ? '-' : ts.toLocaleTimeString()}`;
    }
  } catch (e) {
    console.warn('Live refresh error', e);
  } finally {
    setTimeout(refresh, 500); // refresh every 500ms
  }
}
refresh();

// ======== Focus Control ========
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

// ======== Take Picture ========
snapBtn.addEventListener('click', async () => {
  paused = true;

  try {
    const res = await fetch('/video_snapshot', { cache: 'no-store' });
    const data = await res.json();

    if (data.error) { alert('Snapshot failed: ' + data.error); return; }

    // Display annotated snapshot
    streamImg.src = "data:image/jpeg;base64," + data.image_base64;

    // Flash animation (keeps image large)
    streamImg.style.transition = 'opacity 0.3s ease';
    streamImg.style.opacity = '0.6';
    setTimeout(() => {
      streamImg.style.opacity = '1';
    }, 200);

    // Update measurements table
    tableBody.innerHTML = '';
    data.holes_mm.forEach((d, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${i + 1}</td><td>${d.toFixed(2)}</td>`;
      tableBody.appendChild(tr);
    });

    const ts = new Date((data.timestamp || 0) * 1000);
    meta.textContent = `Photo taken at ${ts.toLocaleTimeString()}`;
  } catch(e) {
    alert('Snapshot failed');
  }
});

// ======== Reset Button ========
resetBtn.addEventListener('click', () => {
  paused = false;

  // Clear measurements table
  tableBody.innerHTML = '';

  // Reset meta
  meta.textContent = 'Live feed resumed';

  // Reset image animation
  streamImg.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
  streamImg.style.transform = 'scale(1) translateY(0)';
  streamImg.style.opacity = '1';

  // Restart live feed
  streamImg.src = '/video';
});