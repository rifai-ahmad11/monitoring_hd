let metadataRows = [];
let metadataView = "active";
let pendingArchiveMachineId = null;

const form = document.getElementById("metadataForm");
const fields = {
  editing: document.getElementById("editingMachineId"),
  machineId: document.getElementById("machineId"),
  serialNumber: document.getElementById("serialNumber"),
  hospitalName: document.getElementById("hospitalName"),
  unitNumber: document.getElementById("unitNumber"),
  region: document.getElementById("region"),
  subregion: document.getElementById("subregion"),
  category: document.getElementById("category"),
  installationDate: document.getElementById("installationDate")
};

function clearForm() {
  form.reset();
  fields.editing.value = "";
  fields.machineId.disabled = HD_APP.role === "viewer";
}

function visibleRows() {
  return metadataRows.filter((row) => metadataView === "archived" ? row.is_archived : !row.is_archived);
}

function populateFilters() {
  const regionFilter = document.getElementById("regionFilter");
  const subregionFilter = document.getElementById("subregionFilter");
  const selectedRegion = regionFilter.value;
  const selectedSubregion = subregionFilter.value;
  const source = visibleRows();
  const regions = [...new Set(source.map((row) => row.region))].sort((a, b) => a.localeCompare(b, "id"));
  regionFilter.innerHTML = '<option value="">Semua Region</option>' +
    regions.map((region) => `<option value="${escapeHtml(region)}" ${region === selectedRegion ? "selected" : ""}>${escapeHtml(region)}</option>`).join("");
  const subregions = [...new Set(source
    .filter((row) => !regionFilter.value || row.region === regionFilter.value)
    .map((row) => row.subregion))].sort((a, b) => a.localeCompare(b, "id"));
  subregionFilter.innerHTML = '<option value="">Semua Subregion</option>' +
    subregions.map((subregion) => `<option value="${escapeHtml(subregion)}" ${subregion === selectedSubregion ? "selected" : ""}>${escapeHtml(subregion)}</option>`).join("");
}

function renderTable() {
  const region = document.getElementById("regionFilter").value;
  const subregion = document.getElementById("subregionFilter").value;
  const filtered = visibleRows().filter((row) =>
    (!region || row.region === region) && (!subregion || row.subregion === subregion)
  );
  document.getElementById("activeMetadataCount").textContent = metadataRows.filter((row) => !row.is_archived).length;
  document.getElementById("archivedMetadataCount").textContent = metadataRows.filter((row) => row.is_archived).length;
  document.getElementById("metadataTable").innerHTML = filtered.map((row) => `
    <tr class="${row.is_archived ? "archived-row" : ""}">
      <td>${escapeHtml(row.machine_id)}</td>
      <td>${escapeHtml(row.serial_number)}</td>
      <td>${escapeHtml(row.hospital_name)}</td>
      <td>${row.unit_number}</td>
      <td>${escapeHtml(row.region)}</td>
      <td>${escapeHtml(row.subregion)}</td>
      <td>${escapeHtml(row.category)}${row.is_archived ? '<br><span class="archive-pill">Diarsipkan</span>' : ""}</td>
      <td>${HD_APP.role === "admin" ? `<div class="table-actions">
        ${row.is_archived
          ? `<button class="btn btn-success" data-restore="${escapeHtml(row.machine_id)}"><i class="fas fa-undo" aria-hidden="true"></i> Pulihkan</button>`
          : `<button class="btn btn-muted" data-edit="${escapeHtml(row.machine_id)}"><i class="fas fa-edit" aria-hidden="true"></i> Edit</button>
             <button class="btn btn-danger" data-archive="${escapeHtml(row.machine_id)}"><i class="fas fa-archive" aria-hidden="true"></i> Arsipkan</button>`}
      </div>` : "—"}</td>
    </tr>`).join("") || '<tr><td colspan="8">Tidak ada data.</td></tr>';

  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => editRow(button.dataset.edit)));
  document.querySelectorAll("[data-archive]").forEach((button) => button.addEventListener("click", () => openArchiveModal(button.dataset.archive)));
  document.querySelectorAll("[data-restore]").forEach((button) => button.addEventListener("click", () => restoreRow(button.dataset.restore)));
}

function setMetadataView(view) {
  metadataView = view;
  document.getElementById("activeMetadataTab").classList.toggle("active", view === "active");
  document.getElementById("archivedMetadataTab").classList.toggle("active", view === "archived");
  document.getElementById("regionFilter").value = "";
  document.getElementById("subregionFilter").value = "";
  clearForm();
  populateFilters();
  renderTable();
}

async function loadMetadata() {
  try {
    const data = await apiRequest("/api/metadata");
    metadataRows = data.metadata;
    populateFilters();
    renderTable();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function editRow(machineId) {
  const row = metadataRows.find((item) => item.machine_id === machineId && !item.is_archived);
  if (!row) return;
  fields.editing.value = machineId;
  fields.machineId.value = row.machine_id;
  fields.machineId.disabled = true;
  fields.serialNumber.value = row.serial_number;
  fields.hospitalName.value = row.hospital_name;
  fields.unitNumber.value = row.unit_number;
  fields.region.value = row.region;
  fields.subregion.value = row.subregion;
  fields.category.value = row.category;
  fields.installationDate.value = row.installation_date || "";
  scrollTo({ top: 0, behavior: "smooth" });
}

function openArchiveModal(machineId) {
  const row = metadataRows.find((item) => item.machine_id === machineId);
  if (!row) return;
  pendingArchiveMachineId = machineId;
  document.getElementById("archiveMachineDetails").textContent =
    `${row.serial_number} · ${row.hospital_name} · Unit ${row.unit_number}`;
  document.getElementById("archiveNote").value = "";
  document.getElementById("archiveModal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("archiveNote").focus();
}

function closeArchiveModal() {
  document.getElementById("archiveModal").classList.add("hidden");
  document.body.style.overflow = "";
  pendingArchiveMachineId = null;
}

async function archiveRow(event) {
  event.preventDefault();
  if (!pendingArchiveMachineId) return;
  const archiveNote = document.getElementById("archiveNote").value.trim();
  if (!archiveNote) {
    showToast("Alasan arsip wajib diisi", "error");
    return;
  }
  try {
    await apiRequest(`/api/metadata/${encodeURIComponent(pendingArchiveMachineId)}/archive`, {
      method: "POST",
      body: JSON.stringify({ archive_note: archiveNote })
    });
    closeArchiveModal();
    await loadMetadata();
    showToast("Mesin berhasil diarsipkan", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function restoreRow(machineId) {
  const row = metadataRows.find((item) => item.machine_id === machineId);
  if (!row || !window.confirm(`Pulihkan ${row.serial_number} ke ${row.region} / ${row.subregion}?`)) return;
  try {
    await apiRequest(`/api/metadata/${encodeURIComponent(machineId)}/restore`, { method: "POST" });
    await loadMetadata();
    showToast("Mesin dipulihkan ke region dan subregion asal", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const editingId = fields.editing.value;
  const payload = {
    machine_id: fields.machineId.value,
    serial_number: fields.serialNumber.value,
    hospital_name: fields.hospitalName.value,
    unit_number: fields.unitNumber.value,
    region: fields.region.value,
    subregion: fields.subregion.value,
    category: fields.category.value,
    installation_date: fields.installationDate.value
  };
  try {
    await apiRequest(editingId ? `/api/metadata/${encodeURIComponent(editingId)}` : "/api/metadata", {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(payload)
    });
    clearForm();
    await loadMetadata();
    showToast("Metadata berhasil disimpan", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.getElementById("archiveForm").addEventListener("submit", archiveRow);
document.getElementById("cancelArchive").addEventListener("click", closeArchiveModal);
document.getElementById("cancelArchiveTop").addEventListener("click", closeArchiveModal);
document.getElementById("archiveModal").addEventListener("click", (event) => {
  if (event.target.id === "archiveModal") closeArchiveModal();
});
document.getElementById("activeMetadataTab").addEventListener("click", () => setMetadataView("active"));
document.getElementById("archivedMetadataTab").addEventListener("click", () => setMetadataView("archived"));
document.getElementById("clearMetadata").addEventListener("click", clearForm);
document.getElementById("regionFilter").addEventListener("change", () => { populateFilters(); renderTable(); });
document.getElementById("subregionFilter").addEventListener("change", renderTable);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeArchiveModal(); });
loadMetadata();
