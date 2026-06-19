"""
Allora Density Analysis — FastAPI + HTMX + Jinja web app.

Reuses the existing engine unchanged:
  * Calculations.calculate_totals  (the density math)
  * reports.generate_pdf_report / generate_excel_report  (branded reports)
  * branding.py                    (palette + AlloraPDF)

Run locally / on the Mac mini:
    uvicorn webapp:app --host 0.0.0.0 --port 8000
On Vercel it is imported by api/index.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from Calculations import calculate_totals
from reports import generate_pdf_report, generate_excel_report

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"

app = FastAPI(title="Allora Density Analysis")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --------------------------------------------------------------------------- #
# Form parsing  (reconstruct the plot list the engine expects)
# --------------------------------------------------------------------------- #
def _num(value: str | None, default: float = 0.0) -> float:
    """Parse a possibly comma-formatted numeric string; never raises."""
    if value is None:
        return default
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else default
    except ValueError:
        return default


def _parse_form(form) -> tuple[list[dict], float, bool, str]:
    """Turn the flat HTML form into (plots, total_price, efficiency, project_name)."""
    plot_indices = sorted({
        int(re.match(r"p(\d+)_size", k).group(1))
        for k in form if re.match(r"p\d+_size", k)
    })

    plots: list[dict] = []
    total_each = 0.0
    for p in plot_indices:
        g = lambda name, d="": form.get(f"p{p}_{name}", d)
        parceled = f"p{p}_parceled" in form

        zone_indices = sorted({
            int(m.group(1))
            for k in form if (m := re.match(rf"p{p}_z(\d+)_pct", k))
        })
        zones = []
        for z in zone_indices:
            pct = _num(form.get(f"p{p}_z{z}_pct"))
            if pct > 0:
                zones.append({
                    "percentage": pct,
                    "density_factor": _num(form.get(f"p{p}_z{z}_density")),
                    "density_type": form.get(f"p{p}_z{z}_type", "Residential"),
                })
        if not zones:
            zones = [{"percentage": 100, "density_factor": 0,
                      "density_type": "Residential"}]

        plots.append({
            "serial_number": g("serial") or f"Plot-{p + 1}",
            "plot_size": _num(g("size")),
            "is_parceled": parceled,
            "road_deduction_percent": 0 if parceled else _num(g("road")),
            "zones": zones,
            "coverage_percent": _num(g("coverage")),
            "max_height": _num(g("maxh")),
            "floor_height": _num(g("floorh")),
        })
        total_each += _num(g("price"))

    price_mode = form.get("price_mode", "each")
    total_price = _num(form.get("total_price")) if price_mode == "total" else total_each
    efficiency = "efficiency" in form
    project_name = form.get("project_name") or "Untitled Project"
    return plots, total_price, efficiency, project_name


def _compute(form):
    plots, total_price, efficiency, project_name = _parse_form(form)
    results = calculate_totals(plots, efficiency, "Proportional", [])
    tba = results["total_buildable_area"]
    price_per_m2 = (total_price / tba) if tba else 0
    return results, total_price, price_per_m2, project_name


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/calculate")
async def calculate(request: Request):
    form = await request.form()
    results, total_price, price_per_m2, project_name = _compute(form)
    ctx = {
        "r": results,
        "total_price": total_price,
        "price_per_m2": price_per_m2,
        "project_name": project_name,
        "deductions": results["total_road_deduction"] + results["total_green_deduction"],
    }
    # HTMX swaps in the bare partial; a native submit (HTMX unavailable / no-JS)
    # gets a full, fully-styled page instead of an unstyled fragment.
    template = "_results.html" if request.headers.get("HX-Request") else "results_page.html"
    return templates.TemplateResponse(request, template, ctx)


@app.post("/report.pdf")
async def report_pdf(request: Request):
    form = await request.form()
    results, total_price, price_per_m2, project_name = _compute(form)
    pdf = generate_pdf_report(results, total_price, price_per_m2, project_name)
    fname = re.sub(r"[^\w\-]+", "_", project_name).strip("_") or "density"
    return StreamingResponse(
        pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}_density.pdf"'},
    )


@app.post("/report.xlsx")
async def report_xlsx(request: Request):
    form = await request.form()
    results, total_price, price_per_m2, project_name = _compute(form)
    xl = generate_excel_report(results, total_price, price_per_m2)
    fname = re.sub(r"[^\w\-]+", "_", project_name).strip("_") or "density"
    return Response(
        content=xl.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}_density.xlsx"'},
    )
