/* Site massing — KML drag & drop, and re-run the massing whenever a
   parameter changes (once a plot boundary has been loaded). */
(() => {
  "use strict";
  const form = document.getElementById("site-form");
  if (!form) return;
  const drop = document.getElementById("drop");
  const input = document.getElementById("kml");

  let timer;
  function run(delay = 450) {
    if (!input.files.length) return;
    clearTimeout(timer);
    timer = setTimeout(() => htmx.trigger(form, "recalc"), delay);
  }

  function showFile() {
    const f = input.files[0];
    drop.classList.toggle("has-file", !!f);
    document.getElementById("drop-title").textContent = f ? f.name : "Drop a KML file here";
    document.getElementById("drop-sub").textContent = f
      ? "Click or drop another file to replace it"
      : "or click to choose · export from Google Earth or the DLS portal";
  }

  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => {
    e.preventDefault(); drop.classList.add("over");
  }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!e.dataTransfer.files.length) return;
    input.files = e.dataTransfer.files;
    showFile(); run(0);
  });

  form.addEventListener("input", () => run());
  form.addEventListener("change", (e) => {
    if (e.target === input) showFile();
    run(0);
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); run(0); });
})();
