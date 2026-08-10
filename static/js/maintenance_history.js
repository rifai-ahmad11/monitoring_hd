const historyState = { page: 1, pages: 1, perPage: 50 };

const historyFields = {
  dateFrom: document.getElementById("dateFrom"),
  dateTo: document.getElementById("dateTo"),
  search: document.getElementById("historySearch"),
  region: document.getElementById("historyRegion"),
  subregion: document.getElementById("historySubregion"),
  item: document.getElementById("historyItem"),
  performer: document.getElementById("historyPerformer")
};

function formatMaintenanceDate(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    timeZone: "Asia/Jakarta",
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(iso)) + " WIB";
}

function fillSelect(select, placeholder, values, mapper = (value) => ({ value, label: value })) {
  const selected = select.value;
  select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + values.map((entry) => {
    const option = mapper(entry);
    return `<option value="${escapeHtml(option.value)}" ${option.value === selected ? "selected" : ""}>${escapeHtml(option.label)}</option>`;
  }).join("");
}

async function loadFilterOptions() {
  try {
    const data = await apiRequest("/api/maintenance-history/filters");
    fillSelect(historyFields.region, "Semua Region", data.regions);
    fillSelect(historyFields.subregion, "Semua Subregion", data.subregions);
    fillSelect(historyFields.item, "Semua Item", data.items, (item) => ({ value: item.item_code, label: item.name }));
    fillSelect(historyFields.performer, "Semua User", data.performers);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function currentQuery() {
  const query = new URLSearchParams({
    page: String(historyState.page),
    per_page: String(historyState.perPage)
  });
  const values = {
    date_from: historyFields.dateFrom.value,
    date_to: historyFields.dateTo.value,
    search: historyFields.search.value.trim(),
    region: historyFields.region.value,
    subregion: historyFields.subregion.value,
    item_code: historyFields.item.value,
    performed_by: historyFields.performer.value
  };
  Object.entries(values).forEach(([key, value]) => { if (value) query.set(key, value); });
  return query;
}

function renderHistory(rows, pagination) {
  const table = document.getElementById("maintenanceHistoryTable");
  table.innerHTML = rows.map((row) => `
    <tr>
      <td class="history-date">${escapeHtml(formatMaintenanceDate(row.timestamp))}</td>
      <td>
        <strong>${escapeHtml(row.serial_number)}</strong>
        <small>${escapeHtml(row.machine_id)} · ${escapeHtml(row.region)} / ${escapeHtml(row.subregion)}</small>
      </td>
      <td>${escapeHtml(row.item_name)}</td>
      <td><span class="performed-pill">${escapeHtml(row.performed_by)}</span></td>
      <td class="history-note">${escapeHtml(row.description)}</td>
    </tr>`).join("") || '<tr><td colspan="5">Belum ada riwayat maintenance yang sesuai.</td></tr>';

  historyState.page = pagination.page;
  historyState.pages = pagination.pages;
  document.getElementById("historyTotal").textContent = `${pagination.total} catatan`;
  document.getElementById("historyPageInfo").textContent = `Halaman ${pagination.page} dari ${pagination.pages}`;
  document.getElementById("historyPrevious").disabled = pagination.page <= 1;
  document.getElementById("historyNext").disabled = pagination.page >= pagination.pages;
}

async function loadHistory() {
  try {
    const data = await apiRequest(`/api/maintenance-history?${currentQuery()}`);
    renderHistory(data.history, data.pagination);
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.getElementById("historyFilterForm").addEventListener("submit", (event) => {
  event.preventDefault();
  historyState.page = 1;
  loadHistory();
});

document.getElementById("resetHistoryFilter").addEventListener("click", () => {
  document.getElementById("historyFilterForm").reset();
  historyState.page = 1;
  loadHistory();
});

document.getElementById("historyPrevious").addEventListener("click", () => {
  if (historyState.page > 1) {
    historyState.page -= 1;
    loadHistory();
  }
});

document.getElementById("historyNext").addEventListener("click", () => {
  if (historyState.page < historyState.pages) {
    historyState.page += 1;
    loadHistory();
  }
});

Promise.all([loadFilterOptions(), loadHistory()]);
