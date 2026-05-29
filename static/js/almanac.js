async function loadMoonPhase() {
  document.getElementById('moonLoading').classList.remove('d-none');
  try {
    const res = await fetch('/api/moon-phase');
    const data = await res.json();
    if (data.error) {
      document.getElementById('moonError').textContent = data.error;
      document.getElementById('moonError').classList.remove('d-none');
      return;
    }
    document.getElementById('moonPhase').textContent = data.curphase;
    document.getElementById('moonIllum').textContent = data.fracillum;
    document.getElementById('moonGuidance').textContent = data.guidance;
    const ul = document.getElementById('moonUpcoming');
    ul.innerHTML = data.upcoming.map(p =>
      `<li>${escHtml(p.phase)}: ${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')} at ${escHtml(p.time)} UTC</li>`
    ).join('');
    document.getElementById('moonResults').classList.remove('d-none');
  } catch (e) {
    showToast('Failed to load moon phase: ' + e.message, 'danger');
    document.getElementById('moonError').textContent = 'Moon phase data temporarily unavailable.';
    document.getElementById('moonError').classList.remove('d-none');
  } finally {
    document.getElementById('moonLoading').classList.add('d-none');
  }
}

async function loadFrostForecast() {
  const zip = document.getElementById('zipInput').value.trim();
  const zipErrorEl = document.getElementById('zipError');

  // AC12: client-side validation
  if (!zip || !/^\d{5}$/.test(zip)) {
    zipErrorEl.textContent = 'Please enter a valid 5-digit ZIP code.';
    zipErrorEl.classList.remove('d-none');
    return;
  }
  zipErrorEl.classList.add('d-none');

  const btn = document.getElementById('frostBtn');
  btn.disabled = true;
  document.getElementById('frostLoading').classList.remove('d-none');
  document.getElementById('frostResults').classList.add('d-none');
  document.getElementById('frostError').classList.add('d-none');

  try {
    const res = await fetch('/api/frost-forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zip }),
    });
    const data = await res.json();
    if (data.error) {
      document.getElementById('frostError').textContent = data.error;
      document.getElementById('frostError').classList.remove('d-none');
      return;
    }
    document.getElementById('frostLocation').textContent =
      escHtml(data.location) + (data.timezone ? ` (${escHtml(data.timezone)})` : '');
    const tbody = document.getElementById('frostTable');
    tbody.innerHTML = data.forecast.map(d => {
      const rowClass = d.frost_risk ? 'table-danger' : '';
      const flag = d.frost_risk ? ' <span class="badge bg-danger">Frost Risk</span>' : '';
      return `<tr class="${rowClass}"><td>${escHtml(d.date)}</td><td>${d.min_temp_f}°F${flag}</td></tr>`;
    }).join('');
    document.getElementById('frostResults').classList.remove('d-none');
  } catch (e) {
    showToast('Failed to load frost forecast: ' + e.message, 'danger');
    document.getElementById('frostError').textContent = 'Forecast data temporarily unavailable.';
    document.getElementById('frostError').classList.remove('d-none');
  } finally {
    btn.disabled = false;
    document.getElementById('frostLoading').classList.add('d-none');
  }
}

document.addEventListener('DOMContentLoaded', loadMoonPhase);
document.getElementById('frostBtn').addEventListener('click', loadFrostForecast);
