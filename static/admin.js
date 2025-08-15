(function () {
    const $ = (sel) => document.querySelector(sel);
    const qs = (sel) => Array.from(document.querySelectorAll(sel));
  
    const state = {
      page: 1,
      pageSize: 20,
    };
  
    function fmtAddr(row) {
      const parts = [row.addressLine1, row.addressLine2, row.landmark].filter(Boolean);
      return parts.join(", ");
    }
  
    function badge(status) {
      return `<span class="badge ${status}">${status}</span>`;
    }
  
    async function load() {
      const q = $("#search").value.trim();
      const status = $("#status").value;
      const url = new URL(ADMIN.listUrl, window.location.origin);
      url.searchParams.set("status", status);
      if (q) url.searchParams.set("q", q);
      url.searchParams.set("page", state.page);
      url.searchParams.set("page_size", state.pageSize);
  
      const res = await fetch(url.toString(), { credentials: "include" });
      if (!res.ok) {
        if (res.status === 401) { window.location.href = "/admin/login"; return; }
        alert("Failed to load orders"); return;
      }
      const data = await res.json();
      renderTable(data.items);
      const pages = Math.max(1, Math.ceil(data.total / data.page_size));
      $("#pageinfo").textContent = `Page ${data.page} of ${pages} • ${data.total} total`;
      $("#prev").disabled = state.page <= 1;
      $("#next").disabled = state.page >= pages;
    }
  
    function renderTable(items) {
      const tbody = $("#orders-table tbody");
      tbody.innerHTML = items.map(row => {
        const labelUrl = `${ADMIN.labelBase}/${row.id}/label`;
        return `<tr>
          <td>${row.id}</td>
          <td>${new Date(row.created_at).toLocaleString()}</td>
          <td>${row.name}<br/><small>${row.email}</small></td>
          <td>${row.phone}</td>
          <td>${fmtAddr(row)}</td>
          <td>${row.city}, ${row.state}</td>
          <td>${row.pincode}</td>
          <td>${row.quantity}</td>
          <td>${badge(row.status)}</td>
          <td>
            <a href="${labelUrl}" target="_blank">Label</a>
            ${
              row.status !== "shipped"
                ? `<button data-act="ship" data-id="${row.id}">Mark Shipped</button>`
                : ""
            }
          </td>
        </tr>`;
      }).join("");
  
      // bind ship buttons
      qs('button[data-act="ship"]').forEach(btn => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          const form = new FormData();
          form.set("status", "shipped");
          const res = await fetch(`/admin/orders/${id}/status`, {
            method: "POST",
            credentials: "include",
            body: form
          });
          if (res.ok) load();
          else alert("Failed to update status");
        });
      });
    }
  
    // events
    $("#refresh").addEventListener("click", () => { state.page = 1; load(); });
    $("#status").addEventListener("change", () => { state.page = 1; load(); });
    $("#search").addEventListener("keyup", (e) => { if (e.key === "Enter") { state.page = 1; load(); }});
    $("#prev").addEventListener("click", () => { state.page = Math.max(1, state.page - 1); load(); });
    $("#next").addEventListener("click", () => { state.page = state.page + 1; load(); });
  
    // initial
    load();
  })();
  