async function researchPrograms() {
  const state = document.getElementById('stateSelect').value;
  const farmType = document.getElementById('farmTypeSelect').value;
  const county = document.getElementById('countySelect').value;

  if (!state || !farmType) {
    showToast('Please select both a state and farm type.', 'warning');
    return;
  }

  document.getElementById('programsResults').classList.add('d-none');
  document.getElementById('programsEmpty').classList.add('d-none');
  document.getElementById('programsLoading').classList.remove('d-none');
  document.getElementById('researchBtn').disabled = true;

  try {
    const res = await fetch('/api/programs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, farm_type: farmType, county }),
    });
    const data = await res.json();
    renderPrograms(data.programs, state, farmType, county);
    updateLastUpdated(data.cached_at);
  } catch (e) {
    showToast('Failed to load programs: ' + e.message, 'danger');
    document.getElementById('programsEmpty').classList.remove('d-none');
  } finally {
    document.getElementById('programsLoading').classList.add('d-none');
    document.getElementById('researchBtn').disabled = false;
  }
}

function programCard(p, i) {
  const level = (p.level || 'federal').toLowerCase();
  const badgeClass = level === 'federal' ? 'level-federal' :
                     level === 'state'   ? 'level-state'   : 'level-local';
  const levelLabel = level.charAt(0).toUpperCase() + level.slice(1);

  const website = p.website
    ? `<a href="${escHtml(p.website)}" target="_blank" class="btn btn-sm btn-outline-success mt-2">
         <i class="bi bi-box-arrow-up-right me-1"></i>Official Website
       </a>`
    : '';

  const docs = Array.isArray(p.documents_needed) && p.documents_needed.length
    ? `<ul class="doc-list ps-3 mb-0">${p.documents_needed.map(d => `<li>${escHtml(d)}</li>`).join('')}</ul>`
    : '<span class="text-muted">Not specified</span>';

  const deadline = p.deadline
    ? `<span class="badge bg-secondary">${escHtml(p.deadline)}</span>`
    : '';

  return `
      <div class="accordion-item mb-2 border rounded shadow-sm">
        <h2 class="accordion-header">
          <button class="accordion-button collapsed rounded" type="button"
                  data-bs-toggle="collapse" data-bs-target="#prog-${i}">
            <span class="badge ${badgeClass} text-white me-2">${levelLabel}</span>
            <strong>${escHtml(p.program_name)}</strong>
            <span class="text-muted ms-2 small">&mdash; ${escHtml(p.agency)}</span>
            <span class="ms-auto me-3">${deadline}</span>
          </button>
        </h2>
        <div id="prog-${i}" class="accordion-collapse collapse">
          <div class="accordion-body">
            <p>${escHtml(p.description)}</p>
            <div class="row g-3">
              <div class="col-md-6">
                <h6 class="text-success"><i class="bi bi-person-check me-1"></i>Eligibility</h6>
                <p class="mb-0">${escHtml(p.eligibility || 'See agency website')}</p>
              </div>
              <div class="col-md-6">
                <h6 class="text-success"><i class="bi bi-clipboard-check me-1"></i>How to Apply</h6>
                <p class="mb-0">${escHtml(p.how_to_apply || 'Contact the administering agency')}</p>
              </div>
              <div class="col-12">
                <h6 class="text-success"><i class="bi bi-file-earmark-text me-1"></i>Documents Needed</h6>
                ${docs}
              </div>
            </div>
            ${website}
          </div>
        </div>
      </div>`;
}

function renderPrograms(programs, state, farmType, county) {
  const accordion = document.getElementById('programsAccordion');
  const heading = document.getElementById('resultsHeading');

  const location = county
    ? (state === 'Alaska' ? `${county}, ${state}` : `${county} County, ${state}`)
    : state;
  heading.textContent = `${programs.length} program${programs.length !== 1 ? 's' : ''} found for ${farmType} in ${location}`;

  accordion.innerHTML = programs.map((p, i) => programCard(p, i)).join('');

  document.getElementById('programsResults').classList.remove('d-none');
}

async function refreshPrograms() {
  const state = document.getElementById('stateSelect').value;
  const farmType = document.getElementById('farmTypeSelect').value;
  const county = document.getElementById('countySelect').value;

  if (!state || !farmType) {
    showToast('Please select both a state and farm type.', 'warning');
    return;
  }

  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Refreshing...';

  try {
    const res = await fetch('/api/programs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, farm_type: farmType, county, force_refresh: true }),
    });
    const data = await res.json();
    renderPrograms(data.programs, state, farmType, county);
    updateLastUpdated(data.cached_at);
  } catch (e) {
    showToast('Failed to load programs: ' + e.message, 'danger');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>Refresh';
  }
}

function updateLastUpdated(cachedAt) {
  const el = document.getElementById('lastUpdated');
  if (!cachedAt) {
    el.textContent = 'Not yet searched';
    return;
  }
  const diff = Math.floor((Date.now() - new Date(cachedAt).getTime()) / 1000);
  let label;
  if (diff < 60) {
    label = 'Updated just now';
  } else if (diff < 3600) {
    label = `Updated ${Math.floor(diff / 60)} minute${Math.floor(diff / 60) !== 1 ? 's' : ''} ago`;
  } else if (diff < 86400) {
    label = `Updated ${Math.floor(diff / 3600)} hour${Math.floor(diff / 3600) !== 1 ? 's' : ''} ago`;
  } else {
    label = `Updated ${Math.floor(diff / 86400)} day${Math.floor(diff / 86400) !== 1 ? 's' : ''} ago`;
  }
  el.textContent = label;
}

function clearResults() {
  document.getElementById('lastUpdated').textContent = 'Not yet searched';
  document.getElementById('programsResults').classList.add('d-none');
  document.getElementById('programsEmpty').classList.remove('d-none');
  document.getElementById('stateSelect').value = '';
  document.getElementById('farmTypeSelect').value = '';
  const sel = document.getElementById('countySelect');
  sel.innerHTML = '<option value="">-- Select state first --</option>';
  sel.disabled = true;
}

document.getElementById('stateSelect').addEventListener('change', async function () {
  const state = this.value;
  const sel = document.getElementById('countySelect');
  sel.innerHTML = '<option value="">-- Select state first --</option>';
  sel.disabled = true;
  if (!state) return;
  try {
    const res = await fetch('/api/counties/' + encodeURIComponent(state));
    const counties = await res.json();
    sel.innerHTML = '<option value="">-- All counties (optional) --</option>' +
      counties.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
    sel.disabled = false;
  } catch (e) {
    showToast('Failed to load counties: ' + e.message, 'warning');
  }
});

// Show initial empty state
document.getElementById('programsEmpty').classList.remove('d-none');
