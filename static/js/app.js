/* Allora Density Analysis — form builder, autosave and live recalculation.
   The server does all the maths; this file builds the form, keeps a JSON
   copy of it in localStorage and asks HTMX to recalculate on every change. */
(() => {
  "use strict";
  const form = document.getElementById("density-form");
  if (!form) return;

  const STORE = "allora-density-scenario-v2";
  const plotsEl = document.getElementById("plots");
  const plotTpl = document.getElementById("plot-tpl").innerHTML;
  const zoneTpl = document.getElementById("zone-tpl").innerHTML;
  let plotSeq = 0; // ever-increasing, keeps field names unique across removals

  const DEFAULT_ZONE = { type: "Residential", pct: 100, density: 50, coverage: 50 };
  const DEFAULT_PLOT = { serial: "", size: "1,000", price: "0", status: "parceled",
                         road: 10, maxh: 15, floorh: 3, zones: [DEFAULT_ZONE] };
  const DEFAULT = { project_name: "New project", price_mode: "each", total_price: "0",
                    efficiency: false, plots: [DEFAULT_PLOT] };

  const fill = (tpl, map) =>
    Object.entries(map).reduce((s, [k, v]) => s.split(k).join(v), tpl);
  const clone = (o) => JSON.parse(JSON.stringify(o));

  // ---- number formatting (thousands separators on money / area fields) ----
  const fmt = (v) => {
    const s = String(v ?? "").replace(/[^\d.]/g, "");
    if (s === "") return "";
    const [i, d] = s.split(".");
    return Number(i || 0).toLocaleString("en-US") + (d !== undefined ? "." + d.slice(0, 2) : "");
  };

  // ---- recalculation (debounced) -----------------------------------------
  let timer;
  function changed(delay = 350) {
    clearTimeout(timer);
    timer = setTimeout(() => {
      save();
      if (window.htmx) htmx.trigger(form, "recalc");
    }, delay);
  }

  // ---- state <-> DOM -------------------------------------------------------
  function readPlot(plotEl) {
    const plot = { zones: [] };
    plotEl.querySelectorAll("[data-k]").forEach((el) => {
      if (el.closest("[data-zone]")) return;
      const k = el.dataset.k;
      if (el.type === "radio") { if (el.checked) plot[k] = el.value; }
      else plot[k] = el.value;
    });
    plotEl.querySelectorAll("[data-zone]").forEach((z) => {
      const zone = {};
      z.querySelectorAll("[data-k]").forEach((el) => (zone[el.dataset.k] = el.value));
      plot.zones.push(zone);
    });
    return plot;
  }

  function readState() {
    return {
      project_name: form.project_name.value,
      price_mode: form.querySelector('input[name="price_mode"]:checked').value,
      total_price: form.total_price.value,
      efficiency: form.efficiency.checked,
      plots: [...plotsEl.querySelectorAll(":scope > .plot")].map(readPlot),
    };
  }

  function setVal(el, value) {
    if (el.type === "radio") el.checked = el.value === value;
    else el.value = el.hasAttribute("data-money") ? fmt(value) : (value ?? "");
  }

  function addZone(plotEl, zone = DEFAULT_ZONE) {
    const zones = plotEl.querySelector("[data-zones]");
    const z = parseInt(zones.dataset.seq || "0", 10) + 1;
    zones.dataset.seq = z;
    zones.insertAdjacentHTML("beforeend", fill(zoneTpl, { "__P__": plotEl.dataset.plot, "__Z__": z }));
    const zEl = zones.lastElementChild;
    zEl.querySelectorAll("[data-k]").forEach((el) => setVal(el, zone[el.dataset.k]));
    return zEl;
  }

  function addPlot(plot = DEFAULT_PLOT, after = null) {
    const p = ++plotSeq;
    const tmp = document.createElement("div");
    tmp.innerHTML = fill(plotTpl, { "__P__": p });
    const plotEl = tmp.firstElementChild;
    if (after) after.after(plotEl); else plotsEl.append(plotEl);

    plotEl.querySelectorAll("[data-k]").forEach((el) => {
      if (!el.closest("[data-zone]")) setVal(el, plot[el.dataset.k]);
    });
    (plot.zones && plot.zones.length ? plot.zones : [DEFAULT_ZONE]).forEach((z) => addZone(plotEl, z));
    syncPlot(plotEl);
    return plotEl;
  }

  function render(state) {
    plotsEl.innerHTML = "";
    form.project_name.value = state.project_name || DEFAULT.project_name;
    form.querySelectorAll('input[name="price_mode"]').forEach((r) => (r.checked = r.value === (state.price_mode || "each")));
    form.total_price.value = fmt(state.total_price);
    form.efficiency.checked = !!state.efficiency;
    (state.plots && state.plots.length ? state.plots : DEFAULT.plots).forEach((pl) => addPlot(pl));
    syncAll();
  }

  // ---- derived UI (no maths beyond simple sums) ---------------------------
  function syncPlot(plotEl) {
    const serial = plotEl.querySelector('[data-k="serial"]').value.trim();
    plotEl.querySelector("[data-name]").textContent = serial || plotEl.dataset.label || "Plot";

    const division = plotEl.querySelector('[data-k="status"][value="division"]').checked;
    plotEl.querySelector("[data-division]").hidden = !division;
    const road = plotEl.querySelector('[data-k="road"]');
    plotEl.querySelector("[data-road-range]").value = road.value || 0;
    plotEl.querySelector("[data-road-out]").textContent = (road.value || 0) + "%";

    const share = [...plotEl.querySelectorAll('[data-k="pct"]')]
      .reduce((s, el) => s + (parseFloat(el.value) || 0), 0);
    const shareEl = plotEl.querySelector("[data-share]");
    const ok = Math.abs(share - 100) < 0.01;
    shareEl.className = "share " + (ok ? "ok" : "bad");
    shareEl.textContent = ok ? "100% allocated ✓"
      : share < 100 ? `${+share.toFixed(2)}% allocated — ${+(100 - share).toFixed(2)}% missing`
      : `${+share.toFixed(2)}% allocated — ${+(share - 100).toFixed(2)}% too much`;
    const many = plotEl.querySelectorAll("[data-zone]").length > 1;
    plotEl.querySelectorAll("[data-remove-zone]").forEach((b) => (b.hidden = !many));
  }

  function syncAll() {
    const plots = plotsEl.querySelectorAll(":scope > .plot");
    plots.forEach((p, i) => { p.dataset.label = "Plot " + (i + 1); syncPlot(p); });
    plots.forEach((p) => (p.querySelector("[data-remove-plot]").hidden = plots.length < 2));
    document.getElementById("plot-count").textContent = plots.length;

    const mode = form.querySelector('input[name="price_mode"]:checked').value;
    form.querySelectorAll(".only-total").forEach((el) => (el.hidden = mode !== "total"));
    form.querySelectorAll(".only-each").forEach((el) => (el.hidden = mode !== "each"));
  }

  // ---- persistence ---------------------------------------------------------
  const savedEl = document.getElementById("saved-state");
  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify(readState()));
      savedEl.textContent = "Saved on this device";
    } catch { savedEl.textContent = ""; }
  }
  function load() {
    try { return JSON.parse(localStorage.getItem(STORE)) || null; } catch { return null; }
  }

  // ---- events --------------------------------------------------------------
  form.addEventListener("click", (e) => {
    const t = e.target;
    const plotEl = t.closest(".plot");
    if (t.closest("[data-remove-plot]")) {
      e.preventDefault();
      const name = plotEl.querySelector("[data-name]").textContent;
      if (confirm(`Remove ${name}?`)) { plotEl.remove(); syncAll(); changed(0); }
    } else if (t.closest("[data-dup-plot]")) {
      e.preventDefault();
      const copy = readPlot(plotEl);
      copy.serial = copy.serial ? copy.serial + " (copy)" : "";
      addPlot(copy, plotEl).open = true;
      syncAll(); changed(0);
    } else if (t.closest("[data-add-zone]")) {
      e.preventDefault();
      const used = [...plotEl.querySelectorAll('[data-k="pct"]')].reduce((s, el) => s + (parseFloat(el.value) || 0), 0);
      addZone(plotEl, { ...DEFAULT_ZONE, pct: Math.max(0, 100 - used) }).querySelector("select").focus();
      syncPlot(plotEl); changed(0);
    } else if (t.closest("[data-remove-zone]")) {
      e.preventDefault();
      t.closest("[data-zone]").remove(); syncPlot(plotEl); changed(0);
    }
  });

  form.addEventListener("input", (e) => {
    const t = e.target;
    const plotEl = t.closest(".plot");
    if (t.matches("[data-road-range]")) plotEl.querySelector('[data-k="road"]').value = t.value;
    if (plotEl) syncPlot(plotEl);
    changed();
  });

  form.addEventListener("change", (e) => {
    if (e.target.name === "price_mode") syncAll();
    if (e.target.hasAttribute("data-money")) e.target.value = fmt(e.target.value);
    const plotEl = e.target.closest(".plot");
    if (plotEl) syncPlot(plotEl);
    changed(0);
  });

  // Enter in a field recalculates instead of reloading the page.
  form.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); changed(0); }
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); changed(0); });

  const newPlot = () => {
    const el = addPlot(); syncAll(); changed(0);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.querySelector('[data-k="serial"]').focus({ preventScroll: true });
  };
  document.getElementById("add-plot").addEventListener("click", newPlot);
  document.getElementById("add-plot-2").addEventListener("click", newPlot);

  // ---- scenario menu --------------------------------------------------------
  const menuBtn = document.getElementById("scenario-btn");
  const menu = document.getElementById("scenario-menu");
  const importInput = document.getElementById("import-file");
  const toggleMenu = (open) => { menu.hidden = !open; menuBtn.setAttribute("aria-expanded", open); };
  menuBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(menu.hidden); });
  document.addEventListener("click", (e) => { if (!menu.contains(e.target)) toggleMenu(false); });

  menu.addEventListener("click", (e) => {
    const action = e.target.dataset.action;
    toggleMenu(false);
    if (action === "export") {
      const state = readState();
      const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
      const name = (state.project_name || "scenario").replace(/[^\w\-]+/g, "_");
      download(blob, `${name}.density.json`);
    } else if (action === "import") {
      importInput.click();
    } else if (action === "reset") {
      if (confirm("Clear all inputs and start a new project?")) { render(clone(DEFAULT)); changed(0); }
    }
  });

  importInput.addEventListener("change", async () => {
    const file = importInput.files[0];
    if (!file) return;
    try {
      const state = JSON.parse(await file.text());
      if (!Array.isArray(state.plots)) throw new Error("no plots");
      render(state); changed(0);
    } catch {
      alert("This file is not a saved density scenario.");
    }
    importInput.value = "";
  });

  // ---- report downloads (results are swapped in by HTMX) -------------------
  function download(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-download]");
    if (!btn) return;
    e.preventDefault();
    const label = btn.textContent;
    btn.textContent = "Preparing…"; btn.disabled = true;
    try {
      const res = await fetch(btn.dataset.download, { method: "POST", body: new FormData(form) });
      if (!res.ok) throw new Error(res.status);
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      download(await res.blob(), m ? m[1] : "report");
    } catch {
      alert("Could not generate the report. Please try again.");
    } finally {
      btn.textContent = label; btn.disabled = false;
    }
  });

  // ---- boot ------------------------------------------------------------------
  render(load() || clone(DEFAULT));
  // htmx binds hx-trigger listeners on DOMContentLoaded (its handler was
  // registered first, so it runs before this one).
  document.addEventListener("DOMContentLoaded", () => htmx.trigger(form, "recalc"));
})();
