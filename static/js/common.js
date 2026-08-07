(function () {
  const toast = document.getElementById("toast");
  let toastTimer;

  window.showToast = function (message, type = "") {
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.className = "toast";
    }, 3200);
  };

  window.apiRequest = async function (url, options = {}) {
    const config = {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    };
    const response = await fetch(url, config);
    let data;
    try {
      data = await response.json();
    } catch {
      data = { ok: false, error: `Server merespons dengan status ${response.status}` };
    }
    if (response.status === 401) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      throw new Error("Sesi login berakhir");
    }
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || "Permintaan gagal");
    }
    return data;
  };

  window.escapeHtml = function (value) {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  };

  window.confirmDelete = function (label) {
    return window.confirm(`Hapus ${label}? Tindakan ini tidak dapat dibatalkan.`);
  };

  if (window.HD_APP?.role === "viewer") {
    document.querySelectorAll(".write-action").forEach((node) => node.remove());
    document.querySelectorAll("form input, form select, form textarea").forEach((node) => {
      node.disabled = true;
    });
  }
})();
