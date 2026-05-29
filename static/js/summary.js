const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
let chart = null;

async function loadSummary() {
  const tbody = document.getElementById('summaryBody');
  const tfoot = document.getElementById('summaryFoot');

  try {
    const res = await fetch('/api/summary');
    const data = await res.json();

    if (data.labels.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="text-center text-muted py-3">
      No data yet. Scan some receipts first.
    </td></tr>`;
      tfoot.innerHTML = '';
      renderChart([], [], []);
      return;
    }

    tbody.innerHTML = data.labels.map((label, i) => `
    <tr>
      <td>${label}</td>
      <td class="text-center">${data.counts[i]}</td>
      <td class="text-end">${fmt.format(data.totals[i])}</td>
    </tr>
  `).join('');

    const grandTotal = data.totals.reduce((a, b) => a + b, 0);
    const grandCount = data.counts.reduce((a, b) => a + b, 0);
    tfoot.innerHTML = `<tr class="fw-bold table-success">
    <td>Total</td>
    <td class="text-center">${grandCount}</td>
    <td class="text-end">${fmt.format(grandTotal)}</td>
  </tr>`;

    renderChart(data.labels, data.totals, data.counts);

  } catch (e) {
    showToast('Failed to load summary: ' + e.message, 'danger');
    tbody.innerHTML = `<tr><td colspan="3" class="text-center text-muted py-3">
      Could not load summary data.
    </td></tr>`;
    tfoot.innerHTML = '';
    renderChart([], [], []);
  }
}

function renderChart(labels, totals, counts) {
  const ctx = document.getElementById('spendChart').getContext('2d');
  if (chart) chart.destroy();

  if (labels.length === 0) {
    ctx.canvas.parentElement.innerHTML =
      '<p class="text-center text-muted py-5">No data to display yet.</p>';
    return;
  }

  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Total Spend',
        data: totals,
        backgroundColor: 'rgba(76, 175, 80, 0.7)',
        borderColor: '#388E3C',
        borderWidth: 1,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: 'Monthly Farm Expenses',
          font: { size: 16, weight: 'bold' }
        },
        tooltip: {
          callbacks: {
            label: ctx => fmt.format(ctx.parsed.y) + ` (${counts[ctx.dataIndex]} receipts)`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: val => '$' + val.toLocaleString()
          }
        }
      }
    }
  });
}

loadSummary();
