let userRows = [];
const userForm = document.getElementById("userForm");
const userFields = {
  editing: document.getElementById("editingUserId"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  role: document.getElementById("role"),
  assigned: document.getElementById("assignedRegions")
};

function clearUserForm() {
  userForm.reset();
  userFields.editing.value = "";
  userFields.password.required = true;
}

function renderUsers() {
  document.getElementById("usersTable").innerHTML = userRows.map((user) => `
    <tr>
      <td><strong>${escapeHtml(user.username)}</strong></td>
      <td><span class="role-pill ${escapeHtml(user.role)}">${escapeHtml(user.role.toUpperCase())}</span></td>
      <td>${user.assigned_regions.length ? user.assigned_regions.map((item) => `<span class="region-pill">${escapeHtml(item)}</span>`).join("") : "—"}</td>
      <td>${HD_APP.role === "admin" ? `<div class="table-actions">
        <button class="btn btn-muted" data-edit="${user.id}"><i class="fas fa-edit" aria-hidden="true"></i> Edit</button>
        <button class="btn btn-danger" data-delete="${user.id}"><i class="fas fa-trash" aria-hidden="true"></i> Hapus</button>
      </div>` : "—"}</td>
    </tr>`).join("") || '<tr><td colspan="4">Tidak ada pengguna.</td></tr>';
  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => editUser(Number(button.dataset.edit))));
  document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => deleteUser(Number(button.dataset.delete))));
}

async function loadUsers() {
  try {
    const data = await apiRequest("/admin/api/users");
    userRows = data.users;
    renderUsers();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function editUser(id) {
  const user = userRows.find((row) => row.id === id);
  if (!user) return;
  userFields.editing.value = id;
  userFields.username.value = user.username;
  userFields.password.value = "";
  userFields.password.required = false;
  userFields.password.placeholder = "Kosongkan jika password tidak diubah";
  userFields.role.value = user.role;
  userFields.assigned.value = user.assigned_regions.join(", ");
  scrollTo({ top: 0, behavior: "smooth" });
}

async function deleteUser(id) {
  const user = userRows.find((row) => row.id === id);
  if (!confirmDelete(`user ${user?.username || id}`)) return;
  try {
    await apiRequest(`/admin/api/users/${id}`, { method: "DELETE" });
    await loadUsers();
    showToast("User berhasil dihapus", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

userFields.role.addEventListener("change", () => {
  const technician = userFields.role.value === "teknisi";
  userFields.assigned.disabled = !technician;
  if (!technician) userFields.assigned.value = "";
});

userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = userFields.editing.value;
  const payload = {
    username: userFields.username.value,
    password: userFields.password.value,
    role: userFields.role.value,
    assigned_regions: userFields.assigned.value
  };
  try {
    await apiRequest(id ? `/admin/api/users/${id}` : "/admin/api/users", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload)
    });
    clearUserForm();
    await loadUsers();
    showToast("User berhasil disimpan", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.getElementById("clearUser").addEventListener("click", clearUserForm);
loadUsers();
