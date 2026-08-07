let metadataRows = [];
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

function populateFilters() {
  const regionFilter = document.getElementById("regionFilter");
  const subregionFilter = document.getElementById("subregionFilter");
  const selectedRegion = regionFilter.value;
  const selectedSubregion = subregionFilter.value;
  const regions = [...new Set(metadataRows.map((row) => row.region))].sort();
  regionFilter.innerHTML = '<option value="">Semua Region</option>' +
    regions.map((region) => `<option ${region === selectedRegion ? "selected" : ""}>${escapeHtml(region)}</option>`).join("");
  const subregions = [...new Set(metadataRows
    .filter((row) => !regionFilter.value || row.region === regionFilter.value)
    .map((row) => row.subregion))].sort();
  subregionFilter.innerHTML = '<option value="">Semua Subregion</option>' +
    subregions.map((region) => `<option ${region === selectedSubregion ? "selected" : ""}>${escapeHtml(region)}</option>`).join("");
}

function renderTable() {
  const region = document.getElementById("regionFilter").value;
  const subregion = document.getElementById("subregionFilter").value;
  const filtered = metadataRows.filter((row) =>
    (!region || row.region === region) && (!subregion || row.subregion === subregion)
  );
  document.getElementById("metadataTable").innerHTML = filtered.map((row) => `
    <tr>
      <td>${escapeHtml(row.machine_id)}</td>
      <td>${escapeHtml(row.serial_number)}</td>
      <td>${escapeHtml(row.hospital_name)}</td>
      <td>${row.unit_number}</td>
      <td>${escapeHtml(row.region)}</td>
      <td>${escapeHtml(row.subregion)}</td>
      <td>${escapeHtml(row.category)}</td>
      <td>${HD_APP.role === "admin" ? `<div class="table-actions">
        <button class="btn btn-muted" data-edit="${escapeHtml(row.machine_id)}"><i class="fas fa-edit" aria-hidden="true"></i> Edit</button>
        <button class="btn btn-danger" data-delete="${escapeHtml(row.machine_id)}"><i class="fas fa-trash" aria-hidden="true"></i> Hapus</button>
      </div>` : "—"}</td>
    </tr>`).join("") || '<tr><td colspan="8">Tidak ada data.</td></tr>';
  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => editRow(button.dataset.edit)));
  document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => deleteRow(button.dataset.delete)));
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
  const row = metadataRows.find((item) => item.machine_id === machineId);
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

async function deleteRow(machineId) {
  if (!confirmDelete(`metadata ${machineId}`)) return;
  try {
    await apiRequest(`/api/metadata/${encodeURIComponent(machineId)}`, { method: "DELETE" });
    await loadMetadata();
    showToast("Metadata berhasil dihapus", "success");
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

document.getElementById("clearMetadata").addEventListener("click", clearForm);
document.getElementById("regionFilter").addEventListener("change", () => { populateFilters(); renderTable(); });
document.getElementById("subregionFilter").addEventListener("change", renderTable);
loadMetadata();
