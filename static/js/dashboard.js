const state = {
  machines: [],
  fetchedAt: Date.now(),
  view: "summary",
  category: null,
  region: null,
  subregion: null,
  hospital: null
};

const elements = {
  pageTitle: document.getElementById("pageTitle"),
  breadcrumb: document.getElementById("breadcrumb"),
  summaryGrid: document.getElementById("summaryGrid"),
  contentTitle: document.getElementById("contentTitle"),
  selectionGrid: document.getElementById("selectionGrid"),
  machineGrid: document.getElementById("machineGrid"),
  emptyState: document.getElementById("emptyState"),
  backButton: document.getElementById("backButton"),
  refreshButton: document.getElementById("refreshButton"),
  categoryNav: document.getElementById("categoryNav")
};

let humidityChartState = { logs: [], points: [] };

function readUrlState() {
  const query = new URLSearchParams(location.search);
  state.view = query.get("view") || "summary";
  state.category = query.get("category");
  state.region = query.get("region");
  state.subregion = query.get("subregion");
  state.hospital = query.get("hospital");
}

function writeUrlState(patch, replace = false) {
  Object.assign(state, patch);
  const query = new URLSearchParams();
  if (state.view !== "summary") query.set("view", state.view);
  for (const key of ["category", "region", "subregion", "hospital"]) {
    if (state[key]) query.set(key, state[key]);
  }
  const url = `${location.pathname}${query.toString() ? `?${query}` : ""}`;
  history[replace ? "replaceState" : "pushState"]({}, "", url);
  render();
}

function filteredMachines(scope = "current") {
  return state.machines.filter((machine) => {
    const meta = machine.metadata;
    if (state.category && meta.category !== state.category) return false;
    if (scope === "category") return true;
    if (state.region && meta.region !== state.region) return false;
    if (state.subregion && meta.subregion !== state.subregion) return false;
    if (state.hospital && meta.hospital_name !== state.hospital) return false;
    return true;
  });
}

function groupBy(items, getter) {
  return items.reduce((groups, item) => {
    const key = getter(item) || "Belum ditentukan";
    (groups[key] ||= []).push(item);
    return groups;
  }, {});
}

function percent(value, total) {
  return total ? Math.round((value / total) * 100) : 0;
}

function renderSummary(machines) {
  const total = machines.length;
  const on = machines.filter((item) => item.status === "running").length;
  const treatment = machines.filter((item) => item.pump_status === "running").length;
  const maintenance = machines.filter((item) => item.maintenance_count > 0).length;
  const cards = [
    { label: "Total Mesin", value: total, percentage: total ? 100 : 0 },
    { label: "HD ON", value: on, percentage: percent(on, total) },
    { label: "In Treatment", value: treatment, percentage: percent(treatment, total) },
    { label: "Need Maintenance", value: maintenance, percentage: percent(maintenance, total) }
  ];
  elements.summaryGrid.innerHTML = cards.map((card) => `
    <article class="summary-card">
      <div>
        <div class="label">${card.label}</div>
        <div class="value">${card.value}</div>
      </div>
      <div class="donut" style="--percentage:${card.percentage}">
        <span>${card.percentage}%</span>
      </div>
    </article>
  `).join("");
}

function levels() {
  if (state.view === "categories" && !state.category) return "categories";
  if (!state.region) return "regions";
  if (!state.subregion) return "subregions";
  if (!state.hospital) return "hospitals";
  return "machines";
}

function titleForLevel(level) {
  if (level === "categories") return "Kategori Mesin";
  if (level === "regions") return state.category ? `Kategori ${state.category}` : "Ringkasan Nasional";
  if (level === "subregions") return state.region;
  if (level === "hospitals") return state.subregion;
  return state.hospital;
}

function renderBreadcrumb(level) {
  const crumbs = [];
  if (state.category) {
    crumbs.push({ label: "Kategori", patch: { view: "categories", category: null, region: null, subregion: null, hospital: null } });
    crumbs.push({ label: state.category, patch: { view: "summary", region: null, subregion: null, hospital: null } });
  } else {
    crumbs.push({ label: "🌐 Nasional", patch: { view: "summary", region: null, subregion: null, hospital: null } });
  }
  if (state.region) crumbs.push({ label: state.region, patch: { subregion: null, hospital: null } });
  if (state.subregion) crumbs.push({ label: state.subregion, patch: { hospital: null } });
  if (state.hospital) crumbs.push({ label: state.hospital, patch: {} });
  if (level === "categories") crumbs.splice(0, crumbs.length, { label: "Kategori", patch: {} });
  elements.breadcrumb.innerHTML = crumbs.map((crumb, index) => {
    const button = `<button data-crumb="${index}">${escapeHtml(crumb.label)}</button>`;
    return `${index ? '<span class="crumb-separator">›</span>' : ""}${button}`;
  }).join("");
  elements.breadcrumb.querySelectorAll("[data-crumb]").forEach((button) => {
    button.addEventListener("click", () => writeUrlState(crumbs[Number(button.dataset.crumb)].patch));
  });
}

function aggregateStatus(machines) {
  return {
    total: machines.length,
    on: machines.filter((m) => m.status === "running").length,
    treatment: machines.filter((m) => m.pump_status === "running").length,
    maintenance: machines.filter((m) => m.maintenance_count > 0).length
  };
}

function renderSelectionCard(label, machines, icon, clickPatch) {
  const stats = aggregateStatus(machines);
  const card = document.createElement("button");
  card.className = "selection-card";
  card.innerHTML = `
    <h4>${escapeHtml(label)}</h4>
    <div class="unit-count">${icon} ${stats.total} ${icon === "⌂" ? "mesin" : "unit"}</div>
    <div class="mini-status">
      <span><i class="dot green"></i>${stats.on}</span>
      <span><i class="dot blue"></i>${stats.treatment}</span>
      <span><i class="dot orange"></i>${stats.maintenance}</span>
    </div>`;
  card.addEventListener("click", () => writeUrlState(clickPatch));
  return card;
}

function renderSelections(level, machines) {
  elements.selectionGrid.innerHTML = "";
  elements.selectionGrid.className = "selection-grid";
  elements.machineGrid.classList.add("hidden");
  elements.selectionGrid.classList.remove("hidden");
  elements.emptyState.classList.add("hidden");

  if (level === "categories") {
    elements.contentTitle.textContent = "Pilih Kategori";
    elements.selectionGrid.classList.add("category-grid");
    ["KSO", "Non-KSO"].forEach((category) => {
      const items = state.machines.filter((m) => m.metadata.category === category);
      const card = renderSelectionCard(category, items, "▣", {
        view: "summary", category, region: null, subregion: null, hospital: null
      });
      card.classList.add("category-card");
      card.insertAdjacentHTML("afterbegin", `<div class="category-icon">${category === "KSO" ? "◆" : "◇"}</div>`);
      elements.selectionGrid.appendChild(card);
    });
    return;
  }

  let groups;
  let icon;
  if (level === "regions") {
    elements.contentTitle.textContent = "Pilih Region";
    groups = groupBy(machines, (m) => m.metadata.region);
    icon = "●";
  } else if (level === "subregions") {
    elements.contentTitle.textContent = "Pilih Subregion";
    groups = groupBy(machines, (m) => m.metadata.subregion);
    icon = "▦";
  } else {
    elements.contentTitle.textContent = "Pilih Rumah Sakit / Klinik";
    groups = groupBy(machines, (m) => m.metadata.hospital_name);
    icon = "⌂";
  }

  Object.entries(groups).sort(([a], [b]) => a.localeCompare(b, "id")).forEach(([label, items]) => {
    const patch = level === "regions"
      ? { region: label, subregion: null, hospital: null }
      : level === "subregions"
        ? { subregion: label, hospital: null }
        : { hospital: label };
    elements.selectionGrid.appendChild(renderSelectionCard(label, items, icon, patch));
  });
  if (!Object.keys(groups).length) elements.emptyState.classList.remove("hidden");
}

function formatDuration(seconds) {
  const safe = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  return [h, m, s].map((part) => String(part).padStart(2, "0")).join(":");
}

function formatWib(iso) {
  if (!iso) return "Belum update";
  return new Intl.DateTimeFormat("id-ID", {
    timeZone: "Asia/Jakarta", day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  }).format(new Date(iso));
}

function renderMachines(machines) {
  elements.contentTitle.textContent = "Daftar Mesin";
  elements.selectionGrid.classList.add("hidden");
  elements.machineGrid.classList.remove("hidden");
  elements.machineGrid.innerHTML = "";
  elements.emptyState.classList.toggle("hidden", machines.length > 0);
  for (const machine of machines) {
    const unit = machine.metadata.unit_number == null ? "?" : machine.metadata.unit_number;
    const card = document.createElement("article");
    card.className = "machine-card";
    card.dataset.machineId = machine.machine_id;
    const elapsed = Math.floor((Date.now() - state.fetchedAt) / 1000);
    const currentActive = machine.current_active_seconds + (machine.status === "running" ? elapsed : 0);
    const currentDialysis = machine.current_dialysis_seconds + (machine.pump_status === "running" ? elapsed : 0);
    card.innerHTML = `
      <div class="machine-header">
        <div>
          <h4>Unit ${unit}</h4>
          <div class="machine-subtitle">${escapeHtml(machine.metadata.hospital_name)}</div>
          <span class="serial">SN: ${escapeHtml(machine.metadata.serial_number)}</span>
        </div>
        <div class="badges">
          ${machine.maintenance_count ? `<button class="badge maintenance" data-maintenance>⚠ ${machine.maintenance_count}</button>` : ""}
          ${machine.pump_status === "running" ? '<span class="badge treatment">TREATMENT</span>' : ""}
          <span class="badge ${machine.status === "running" ? "on" : "off"}">${machine.status === "running" ? "HD ON" : "HD OFF"}</span>
        </div>
      </div>
      <div class="machine-stats">
        <div class="stat-row"><span class="stat-label">Waktu Aktif</span><span class="timer-pill" data-current-active data-base="${machine.current_active_seconds}">${formatDuration(currentActive)}</span></div>
        <div class="stat-row"><span class="stat-label">Total Aktif</span><span class="stat-value" data-total-active data-base="${machine.total_active_seconds}">${formatDuration(machine.total_active_seconds)}</span></div>
        <div class="stat-row"><span class="stat-label">Sesi Aktif Selesai</span><span class="stat-value">${machine.completed_treatments}</span></div>
        <div class="stat-row"><span class="stat-label">Waktu Treatment</span><span class="timer-pill treatment" data-current-treatment data-base="${machine.current_dialysis_seconds}">${formatDuration(currentDialysis)}</span></div>
        <div class="stat-row"><span class="stat-label">Total Treatment</span><span class="stat-value" data-total-treatment data-base="${machine.total_dialysis_seconds}">${formatDuration(machine.total_dialysis_seconds)}</span></div>
        <div class="stat-row"><span class="stat-label">Treatment Selesai</span><span class="stat-value">${machine.completed_dialysis}</span></div>
        <div class="stat-row"><span class="stat-label">Kelembapan</span><span class="stat-value">${machine.humidity == null ? "N/A" : `${Number(machine.humidity).toFixed(1)}%`}</span></div>
      </div>
      <div class="machine-footer">
        <button class="icon-button" title="Ringkasan tegangan" data-voltage>⚡</button>
        <button class="icon-button" title="Grafik kelembapan" data-humidity>💧</button>
        <span class="last-update">Terakhir Update: ${formatWib(machine.last_update)}</span>
      </div>`;
    card.querySelector("[data-maintenance]")?.addEventListener("click", () => openMaintenance(machine));
    card.querySelector("[data-voltage]").addEventListener("click", () => openVoltage(machine));
    card.querySelector("[data-humidity]").addEventListener("click", () => openHumidity(machine));
    elements.machineGrid.appendChild(card);
  }
}

function render() {
  const level = levels();
  const machines = filteredMachines();
  elements.pageTitle.textContent = titleForLevel(level);
  elements.backButton.classList.toggle("hidden", level === "regions" && !state.category || level === "categories");
  document.querySelector("[data-nav='summary']")?.classList.toggle("active", level !== "categories" && !state.category);
  elements.categoryNav.classList.toggle("active", level === "categories" || Boolean(state.category));
  renderBreadcrumb(level);
  renderSummary(level === "categories" ? state.machines : machines);
  if (level === "machines") renderMachines(machines);
  else renderSelections(level, machines);
}

function goBack() {
  const level = levels();
  if (level === "machines") writeUrlState({ hospital: null });
  else if (level === "hospitals") writeUrlState({ subregion: null, hospital: null });
  else if (level === "subregions") writeUrlState({ region: null, subregion: null, hospital: null });
  else if (state.category) writeUrlState({ view: "categories", category: null, region: null, subregion: null, hospital: null });
}

async function loadMachines(showFeedback = false) {
  elements.refreshButton.disabled = true;
  try {
    const data = await apiRequest("/api/machines");
    state.machines = data.machines;
    state.fetchedAt = Date.now();
    render();
    if (showFeedback) showToast("Data berhasil diperbarui", "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.refreshButton.disabled = false;
  }
}

function showModal(id) {
  document.getElementById(id).classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeModals() {
  document.querySelectorAll(".modal-backdrop").forEach((modal) => modal.classList.add("hidden"));
  document.getElementById("humidityTooltip")?.classList.add("hidden");
  document.body.style.overflow = "";
}

function setPopupMachineDetails(elementId, machine) {
  const element = document.getElementById(elementId);
  const metadata = machine.metadata || {};
  const hospital = metadata.hospital_name || "Belum terdaftar";
  const unit = metadata.unit_number ?? "?";
  const serialNumber = metadata.serial_number || machine.machine_id;
  element.dataset.machineId = machine.machine_id;
  element.innerHTML = `
    <span class="modal-location">${escapeHtml(hospital)} · Unit ${escapeHtml(unit)}</span>
    <span class="modal-identifiers"><strong>Machine ID:</strong> ${escapeHtml(machine.machine_id)}</span>
    <span class="modal-identifiers"><strong>Serial Number:</strong> ${escapeHtml(serialNumber)}</span>
  `;
}

function openMaintenance(machine) {
  document.getElementById("maintenanceMachine").textContent =
    `${machine.metadata.hospital_name} · Unit ${machine.metadata.unit_number ?? "?"}`;
  const container = document.getElementById("maintenanceItems");
  container.innerHTML = machine.maintenance_required.map((item) => `
    <article class="maintenance-item">
      <h4>${escapeHtml(item.name)}</h4>
      <p>${escapeHtml(item.description || "Tidak ada deskripsi.")}</p>
      <div class="maintenance-item-footer">
        <span>Ambang: <strong>${escapeHtml(item.threshold_label)}</strong></span>
        ${["admin", "teknisi"].includes(HD_APP.role)
          ? `<button class="btn btn-success" data-done="${escapeHtml(item.item_code)}">✓ Selesai</button>`
          : '<span>Hanya dapat dilihat</span>'}
      </div>
    </article>`).join("");
  container.querySelectorAll("[data-done]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await apiRequest("/maintenance-done", {
          method: "POST",
          body: JSON.stringify({ machine_id: machine.machine_id, item_code: button.dataset.done })
        });
        closeModals();
        await loadMachines();
        showToast("Maintenance berhasil ditandai selesai", "success");
      } catch (error) {
        showToast(error.message, "error");
        button.disabled = false;
      }
    });
  });
  showModal("maintenanceModal");
}

async function openVoltage(machine) {
  setPopupMachineDetails("voltageMachine", machine);
  const container = document.getElementById("voltageSummary");
  container.innerHTML = "<p>Memuat data…</p>";
  showModal("voltageModal");
  try {
    const data = await apiRequest(`/api/voltage-summary/${encodeURIComponent(machine.machine_id)}`);
    const labels = {
      spike: "Spike", overvoltage: "Overvoltage",
      undervoltage: "Undervoltage", error: "Error Tegangan"
    };
    const eventOrder = ["spike", "overvoltage", "undervoltage", "error"];
    container.innerHTML = eventOrder.map((key) => {
      const value = data.summary[key] || { count: 0, last_timestamp: null, last_voltage: null };
      const voltageText = value.last_voltage == null
        ? ""
        : `${key === "spike" ? ">" : ""}${value.last_voltage} V`;
      return `
      <article class="voltage-item">
        <span>${labels[key]}</span>
        <strong>${value.count}</strong>
        <small>${value.last_timestamp ? `Terakhir: ${formatWib(value.last_timestamp)}${voltageText ? ` · ${voltageText}` : ""}` : "Belum ada event"}</small>
      </article>`;
    }).join("");
  } catch (error) {
    container.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

async function openHumidity(machine) {
  setPopupMachineDetails("humidityMachine", machine);
  document.getElementById("humidityTooltip").classList.add("hidden");
  showModal("humidityModal");
  try {
    const data = await apiRequest(`/api/humidity-log/${encodeURIComponent(machine.machine_id)}`);
    drawHumidityChart(data.logs);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function drawHumidityChart(logs, highlightedIndex = null) {
  const canvas = document.getElementById("humidityCanvas");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 900;
  const height = 330;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const margin = { left: 48, right: 18, top: 18, bottom: 40 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  ctx.font = "11px Inter, sans-serif";
  ctx.fillStyle = "#7890aa";
  ctx.strokeStyle = "#e4e9f0";
  ctx.lineWidth = 1;
  for (let y = 0; y <= 100; y += 20) {
    const py = margin.top + plotH - (y / 100) * plotH;
    ctx.beginPath(); ctx.moveTo(margin.left, py); ctx.lineTo(width - margin.right, py); ctx.stroke();
    ctx.fillText(`${y}%`, 10, py + 4);
  }
  if (!logs.length) {
    humidityChartState = { logs: [], points: [] };
    ctx.fillStyle = "#6f8298";
    ctx.font = "14px Inter, sans-serif";
    ctx.fillText("Belum ada data kelembapan.", margin.left + 20, margin.top + plotH / 2);
    return;
  }
  const points = logs.map((row, index) => ({
    x: margin.left + (logs.length === 1 ? plotW / 2 : (index / (logs.length - 1)) * plotW),
    y: margin.top + plotH - (Number(row.humidity) / 100) * plotH
  }));
  humidityChartState = { logs, points };
  ctx.beginPath();
  points.forEach((point, index) => {
    index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y);
  });
  ctx.strokeStyle = "#348fda";
  ctx.lineWidth = 3;
  ctx.lineJoin = "round";
  ctx.stroke();
  const gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
  gradient.addColorStop(0, "rgba(52,143,218,.28)");
  gradient.addColorStop(1, "rgba(52,143,218,0)");
  ctx.lineTo(width - margin.right, margin.top + plotH);
  ctx.lineTo(margin.left, margin.top + plotH);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();
  if (highlightedIndex != null && points[highlightedIndex]) {
    const point = points[highlightedIndex];
    ctx.beginPath();
    ctx.arc(point.x, point.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#348fda";
    ctx.lineWidth = 3;
    ctx.stroke();
  }
  ctx.fillStyle = "#7890aa";
  const first = logs[0]?.timestamp;
  const last = logs.at(-1)?.timestamp;
  if (first) ctx.fillText(formatWib(first), margin.left, height - 13);
  if (last) {
    const label = formatWib(last);
    const measured = ctx.measureText(label).width;
    ctx.fillText(label, width - margin.right - measured, height - 13);
  }
}

function hideHumidityTooltip() {
  const tooltip = document.getElementById("humidityTooltip");
  tooltip.classList.add("hidden");
  if (humidityChartState.logs.length) drawHumidityChart(humidityChartState.logs);
}

function showNearestHumidityPoint(event) {
  const canvas = document.getElementById("humidityCanvas");
  const tooltip = document.getElementById("humidityTooltip");
  if (!humidityChartState.points.length) {
    tooltip.classList.add("hidden");
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const cursor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  let nearestIndex = -1;
  let nearestDistance = Infinity;
  humidityChartState.points.forEach((point, index) => {
    const distance = Math.hypot(point.x - cursor.x, point.y - cursor.y);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });
  if (nearestIndex < 0 || nearestDistance > 20) {
    tooltip.classList.add("hidden");
    drawHumidityChart(humidityChartState.logs);
    return;
  }
  const row = humidityChartState.logs[nearestIndex];
  drawHumidityChart(humidityChartState.logs, nearestIndex);
  const point = humidityChartState.points[nearestIndex];
  const chartWrap = canvas.parentElement;
  const horizontalPadding = 105;
  const left = Math.max(horizontalPadding, Math.min(chartWrap.clientWidth - horizontalPadding, canvas.offsetLeft + point.x));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${canvas.offsetTop + point.y}px`;
  tooltip.classList.toggle("below", point.y < 65);
  tooltip.innerHTML = `<strong>Humidity: ${Number(row.humidity).toFixed(1)}%</strong><span>${escapeHtml(formatWib(row.timestamp))}</span>`;
  tooltip.classList.remove("hidden");
}

function updateTimers() {
  const elapsed = Math.floor((Date.now() - state.fetchedAt) / 1000);
  document.querySelectorAll(".machine-card").forEach((card) => {
    const machine = state.machines.find((m) => m.machine_id === card.dataset.machineId);
    if (!machine) return;
    if (machine.status === "running") {
      card.querySelector("[data-current-active]").textContent = formatDuration(machine.current_active_seconds + elapsed);
      card.querySelector("[data-total-active]").textContent = formatDuration(machine.total_active_seconds + elapsed);
    }
    if (machine.pump_status === "running") {
      card.querySelector("[data-current-treatment]").textContent = formatDuration(machine.current_dialysis_seconds + elapsed);
      card.querySelector("[data-total-treatment]").textContent = formatDuration(machine.total_dialysis_seconds + elapsed);
    }
  });
}

elements.refreshButton.addEventListener("click", () => loadMachines(true));
elements.backButton.addEventListener("click", goBack);
elements.categoryNav.addEventListener("click", () => writeUrlState({
  view: "categories", category: null, region: null, subregion: null, hospital: null
}));
document.querySelectorAll("[data-close-modal]").forEach((button) => button.addEventListener("click", closeModals));
document.querySelectorAll(".modal-backdrop").forEach((modal) => {
  modal.addEventListener("click", (event) => { if (event.target === modal) closeModals(); });
});
document.getElementById("humidityCanvas").addEventListener("mousemove", showNearestHumidityPoint);
document.getElementById("humidityCanvas").addEventListener("mouseleave", hideHumidityTooltip);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModals(); });
document.getElementById("openSidebar").addEventListener("click", () => document.getElementById("sidebar").classList.add("open"));
document.getElementById("closeSidebar").addEventListener("click", () => document.getElementById("sidebar").classList.remove("open"));
window.addEventListener("popstate", () => { readUrlState(); render(); });
window.addEventListener("resize", () => {
  if (!document.getElementById("humidityModal").classList.contains("hidden")) {
    const machineId = document.getElementById("humidityMachine").dataset.machineId;
    const machine = state.machines.find((item) => item.machine_id === machineId);
    if (machine) openHumidity(machine);
  }
});

readUrlState();
loadMachines();
setInterval(updateTimers, 1000);
setInterval(() => loadMachines(false), 30000);
