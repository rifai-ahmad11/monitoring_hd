let configRows = [];
const configForm = document.getElementById("maintenanceForm");
const configFields = {
  editing: document.getElementById("editingConfigId"),
  code: document.getElementById("itemCode"),
  name: document.getElementById("itemName"),
  description: document.getElementById("description"),
  type: document.getElementById("thresholdType"),
  value: document.getElementById("thresholdValue"),
  unit: document.getElementById("timeUnit")
};

function updateTimeUnitVisibility() {
  const visible = configFields.type.value === "time_interval";
  document.getElementById("timeUnitField").classList.toggle("hidden", !visible);
  configFields.unit.required = visible;
}

function clearConfigForm() {
  configForm.reset();
  configFields.editing.value = "";
  configFields.code.disabled = HD_APP.role === "viewer";
  updateTimeUnitVisibility();
}

function thresholdText(row) {
  return row.threshold_type === "treatment_count"
    ? `${row.threshold_value} treatment`
    : `${row.threshold_value} ${row.time_unit}`;
}

function renderConfigs() {
  document.getElementById("maintenanceTable").innerHTML = configRows.map((row) => `
    <tr>
      <td><code>${escapeHtml(row.item_code)}</code></td>
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.description || "—")}</td>
      <td><span class="type-pill ${escapeHtml(row.threshold_type)}">${row.threshold_type === "treatment_count" ? "Treatment Count" : "Time Interval"}</span></td>
      <td>${escapeHtml(thresholdText(row))}</td>
      <td>${HD_APP.role === "admin" ? `<div class="table-actions">
        <button class="btn btn-muted" data-edit="${row.id}"><i class="fas fa-edit" aria-hidden="true"></i> Edit</button>
        <button class="btn btn-danger" data-delete="${row.id}"><i class="fas fa-trash" aria-hidden="true"></i> Hapus</button>
      </div>` : "—"}</td>
    </tr>`).join("") || '<tr><td colspan="6">Tidak ada konfigurasi.</td></tr>';
  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => editConfig(Number(button.dataset.edit))));
  document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => deleteConfig(Number(button.dataset.delete))));
}

async function loadConfigs() {
  try {
    const data = await apiRequest("/api/maintenance-config");
    configRows = data.configs;
    renderConfigs();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function editConfig(id) {
  const row = configRows.find((item) => item.id === id);
  if (!row) return;
  configFields.editing.value = id;
  configFields.code.value = row.item_code;
  configFields.code.disabled = true;
  configFields.name.value = row.name;
  configFields.description.value = row.description;
  configFields.type.value = row.threshold_type;
  configFields.value.value = row.threshold_value;
  configFields.unit.value = row.time_unit || "months";
  updateTimeUnitVisibility();
  scrollTo({ top: 0, behavior: "smooth" });
}

async function deleteConfig(id) {
  const row = configRows.find((item) => item.id === id);
  if (!confirmDelete(`konfigurasi ${row?.item_code || id}`)) return;
  try {
    await apiRequest(`/api/maintenance-config/${id}`, { method: "DELETE" });
    await loadConfigs();
    showToast("Konfigurasi berhasil dihapus", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

configFields.type.addEventListener("change", updateTimeUnitVisibility);
configForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = configFields.editing.value;
  const payload = {
    item_code: configFields.code.value,
    name: configFields.name.value,
    description: configFields.description.value,
    threshold_type: configFields.type.value,
    threshold_value: configFields.value.value,
    time_unit: configFields.type.value === "time_interval" ? configFields.unit.value : null,
    active: true
  };
  try {
    await apiRequest(id ? `/api/maintenance-config/${id}` : "/api/maintenance-config", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload)
    });
    clearConfigForm();
    await loadConfigs();
    showToast("Konfigurasi berhasil disimpan", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.getElementById("clearMaintenance").addEventListener("click", clearConfigForm);
updateTimeUnitVisibility();
loadConfigs();
