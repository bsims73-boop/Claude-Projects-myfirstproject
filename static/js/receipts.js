const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

async function loadReceipts() {
  const res = await fetch('/api/receipts');
  const data = await res.json();

  // Stats bar
  document.getElementById('statsBar').textContent =
    `${data.total_count} receipt${data.total_count !== 1 ? 's' : ''} · Total: ${fmt.format(data.total_spend)}`;

  // Last scan info
  if (data.last_scan) {
    const d = new Date(data.last_scan);
    document.getElementById('lastScanInfo').textContent =
      `Last scan: ${d.toLocaleString()}`;
  }

  const tbody = document.getElementById('receiptsBody');
  const tfoot = document.getElementById('receiptsFoot');

  if (data.receipts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-5">
      <i class="bi bi-inbox display-5 d-block mb-2"></i>
      No receipts yet. Drop images into the <code>receipts/</code> folder and click Scan Now.
    </td></tr>`;
    tfoot.innerHTML = '';
    return;
  }

  tbody.innerHTML = data.receipts.map(r => {
    const isError = r.scan_status === 'error';
    const isPending = r.scan_status === 'pending' || r.scan_status === 'processing';
    const rowClass = isError ? 'table-danger-row' : '';

    const dateCell = r.receipt_date != null ? r.receipt_date : '<span class="text-muted">—</span>';
    const companyCell = r.company_name != null ? r.company_name : '<span class="text-muted">Unknown</span>';
    const amountCell = r.total_amount != null
      ? fmt.format(r.total_amount)
      : '<span class="text-muted">—</span>';

    let imageCell = '<span class="text-muted small">—</span>';
    if (!isError && !isPending) {
      imageCell = `<a href="/receipts/image/${encodeURIComponent(r.filename)}" target="_blank">
        <img src="/receipts/image/${encodeURIComponent(r.filename)}"
             class="receipt-thumb" alt="receipt"
             onerror="this.outerHTML='<span class=\'text-muted small\'>Not found</span>'">
      </a>`;
    }

    let detailsCell = '<span class="text-muted small">—</span>';
    if (!isError && !isPending) {
      detailsCell = `<button class="btn btn-outline-success btn-sm"
        onclick="openDetails(${r.id}, '${escHtml(r.company_name != null ? r.company_name : '')}', '${r.receipt_date != null ? r.receipt_date : ''}')">
        <i class="bi bi-list-ul me-1"></i>Details
      </button>`;
    }

    let statusCell;
    if (isError) {
      statusCell = `<span class="badge bg-danger status-badge" title="${escHtml(r.scan_error || '')}">
        <i class="bi bi-exclamation-triangle me-1"></i>Error
      </span>`;
    } else if (isPending) {
      statusCell = `<span class="badge bg-warning text-dark status-badge">Pending</span>`;
    } else {
      statusCell = `<span class="badge bg-success status-badge"><i class="bi bi-check me-1"></i>Done</span>`;
    }

    return `<tr class="${rowClass}">
      <td>${dateCell}</td>
      <td>${companyCell}</td>
      <td class="text-end">${amountCell}</td>
      <td class="text-center">${imageCell}</td>
      <td class="text-center">${detailsCell}</td>
      <td>${statusCell}</td>
    </tr>`;
  }).join('');

  // Total row
  tfoot.innerHTML = `<tr class="fw-bold">
    <td colspan="2">Total (${data.total_count} receipts)</td>
    <td class="text-end">${fmt.format(data.total_spend)}</td>
    <td colspan="3"></td>
  </tr>`;
}

async function scanNow() {
  const btn = document.getElementById('scanBtn');
  const icon = document.getElementById('scanBtnIcon');
  const spinner = document.getElementById('scanBtnSpinner');

  btn.disabled = true;
  icon.classList.add('d-none');
  spinner.classList.remove('d-none');

  try {
    const res = await fetch('/api/scan', { method: 'POST' });
    const data = await res.json();
    const msg = `Scan complete: ${data.new} new, ${data.processed} scanned, ${data.errors} error(s)`;
    showToast(msg, data.errors > 0 ? 'warning' : 'success');
    await loadReceipts();
  } catch (e) {
    showToast('Scan failed: ' + e.message, 'danger');
  } finally {
    btn.disabled = false;
    icon.classList.remove('d-none');
    spinner.classList.add('d-none');
  }
}

async function openDetails(receiptId, company, date) {
  const modal = new bootstrap.Modal(document.getElementById('lineItemsModal'));
  document.getElementById('modalReceiptInfo').textContent =
    [company, date].filter(Boolean).join(' · ');
  document.getElementById('lineItemsLoading').classList.remove('d-none');
  document.getElementById('lineItemsContent').classList.add('d-none');
  document.getElementById('lineItemsEmpty').classList.add('d-none');
  modal.show();

  try {
    const res = await fetch(`/api/receipts/${receiptId}/items`);
    const items = await res.json();

    document.getElementById('lineItemsLoading').classList.add('d-none');

    if (items.length === 0) {
      document.getElementById('lineItemsEmpty').classList.remove('d-none');
      return;
    }

    const rows = items.map(item => {
      const qty = item.quantity != null ? item.quantity : '—';
      const unit = item.unit_price != null ? fmt.format(item.unit_price) : '—';
      const total = item.line_total != null ? fmt.format(item.line_total) : '—';
      return `<tr>
        <td>${escHtml(item.item_name || '—')}</td>
        <td class="text-center">${qty}</td>
        <td class="text-end">${unit}</td>
        <td class="text-end">${total}</td>
      </tr>`;
    }).join('');

    document.getElementById('lineItemsBody').innerHTML = rows;
    document.getElementById('lineItemsContent').classList.remove('d-none');
  } catch (e) {
    document.getElementById('lineItemsLoading').classList.add('d-none');
    document.getElementById('lineItemsEmpty').textContent = 'Failed to load items: ' + e.message;
    document.getElementById('lineItemsEmpty').classList.remove('d-none');
  }
}

loadReceipts();
