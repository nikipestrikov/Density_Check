/* Allora Density Analysis — progressive form builder.
   HTMX handles calculate/report round-trips; this only builds the form. */
(() => {
  "use strict";
  const form = document.getElementById("density-form");
  if (!form) return;

  const plotsEl = document.getElementById("plots");
  const plotTpl = document.getElementById("plot-tpl").innerHTML;
  const zoneTpl = document.getElementById("zone-tpl").innerHTML;
  let plotSeq = 0; // ever-increasing, keeps field names unique across removals

  const fill = (tpl, map) =>
    Object.entries(map).reduce((s, [k, v]) => s.split(k).join(v), tpl);

  // ---- conditional show/hide (data-toggle / data-invert) ----------------
  function applyToggle(cb) {
    const target = cb.closest(".body, form").querySelector(cb.dataset.toggle);
    if (!target) return;
    const show = cb.dataset.invert !== undefined ? !cb.checked : cb.checked;
    target.hidden = !show;
  }

  // ---- renumber visible plot/zone titles --------------------------------
  function renumber() {
    plotsEl.querySelectorAll(":scope > .plot").forEach((p, i) => {
      p.querySelector(".plot-title").textContent = "Plot " + (i + 1);
      p.querySelectorAll("[data-zone]").forEach((z, j) => {
        z.querySelector(".zh b").textContent = "Zone " + (j + 1);
      });
    });
  }

  // ---- zones -------------------------------------------------------------
  function addZone(plotEl) {
    const p = plotEl.dataset.plot;
    const zones = plotEl.querySelector("[data-zones]");
    const z = (parseInt(zones.dataset.seq || "0", 10)) + 1;
    zones.dataset.seq = z;
    const html = fill(zoneTpl, { "__P__": p, "__Z__": z, "__M__": z });
    zones.insertAdjacentHTML("beforeend", html);
    renumber();
  }

  // ---- plots -------------------------------------------------------------
  function addPlot() {
    const p = ++plotSeq;
    const html = fill(plotTpl, { "__P__": p, "__N__": p });
    plotsEl.insertAdjacentHTML("beforeend", html);
    const plotEl = plotsEl.querySelector(`.plot[data-plot="${p}"]`);
    plotEl.querySelectorAll("input[data-toggle]").forEach(applyToggle);
    addZone(plotEl);            // every plot starts with one zone
    syncPriceMode();
    renumber();
    return plotEl;
  }

  // ---- price mode (each vs total) ---------------------------------------
  function syncPriceMode() {
    const mode = form.querySelector('input[name="price_mode"]:checked').value;
    form.dataset.priceMode = mode;
    form.querySelectorAll(".only-total").forEach(el => el.hidden = mode !== "total");
    form.querySelectorAll(".only-each").forEach(el => el.hidden = mode !== "each");
  }

  // ---- event delegation --------------------------------------------------
  form.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("[data-remove-plot]")) {
      e.preventDefault(); t.closest(".plot").remove(); renumber();
    } else if (t.closest("[data-add-zone]")) {
      e.preventDefault(); addZone(t.closest(".plot"));
    } else if (t.closest("[data-remove-zone]")) {
      e.preventDefault();
      const plotEl = t.closest(".plot");
      if (plotEl.querySelectorAll("[data-zone]").length > 1) {
        t.closest("[data-zone]").remove(); renumber();
      }
    }
  });

  form.addEventListener("change", (e) => {
    if (e.target.matches("input[data-toggle]")) applyToggle(e.target);
    if (e.target.name === "price_mode") syncPriceMode();
  });

  document.getElementById("add-plot").addEventListener("click", addPlot);

  // ---- report downloads (results are swapped in by HTMX) ----------------
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-download]");
    if (!btn) return;
    e.preventDefault();
    const label = btn.textContent;
    btn.textContent = "Preparing…"; btn.disabled = true;
    try {
      const res = await fetch(btn.dataset.download, { method: "POST", body: new FormData(form) });
      if (!res.ok) throw new Error(res.status);
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = m ? m[1] : "report";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      alert("Could not generate the report. Please try again.");
    } finally {
      btn.textContent = label; btn.disabled = false;
    }
  });

  // ---- boot --------------------------------------------------------------
  addPlot();          // start with one plot
  syncPriceMode();
})();
