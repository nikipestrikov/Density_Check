"""
Site massing — import a plot KML and propose a realistic apartment building layout.

v2 (apartments only): instead of slicing the plot into slivers, this places
*rectangular floor plates* inside the buildable envelope, generates three real
building typologies, and keeps the one that fits the plot best.

  Typologies (standard values now, calibrate later):
    * Double-loaded slab    — two unit rows + central corridor, ~21 m deep, eff 82%
    * Single-loaded gallery — one unit row + gallery,           ~12 m deep, eff 80%
    * Point towers          — compact core blocks,              ~24 m square, eff 75%

Pipeline: KML → metres → setback envelope → for each typology place rectangles at
the orientation that maximises floor plate (with daylight separation, capped by
coverage) → estimate GFA / NSA / units → pick the best → SVG.

Indicative feasibility massing only — flat-polygon model, ignores topography.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import LineString, Polygon, box

# Fixed unit catalogue (internal areas, m²) — apartments
UNIT_SIZES = {"1-bed": 50.0, "2-bed": 82.0, "3-bed": 110.0}
DEFAULT_MIX = {"1-bed": 30, "2-bed": 45, "3-bed": 25}  # percent

# Building typologies: depth/side in metres, eff = net internal / GFA
TYPOLOGIES = {
    "Double-loaded slab":    {"kind": "slab",  "depth": 21.0, "eff": 0.82},
    "Single-loaded gallery": {"kind": "slab",  "depth": 12.0, "eff": 0.80},
    "Point towers":          {"kind": "tower", "side": 24.0,  "eff": 0.75},
}
MIN_BUILDING_LEN = 16.0  # m — shorter than this isn't a viable apartment building
ANGLE_STEP = 5           # degrees, orientation search resolution

EARTH_M_PER_DEG_LAT = 110_540.0
EARTH_M_PER_DEG_LON = 111_320.0


# --------------------------------------------------------------------------- #
# KML parsing + projection
# --------------------------------------------------------------------------- #
def parse_kml_rings(data: bytes) -> list[list[tuple[float, float]]]:
    root = ET.fromstring(data)
    rings: list[list[tuple[float, float]]] = []
    for el in root.iter():
        if not el.tag.endswith("coordinates") or not (el.text and el.text.strip()):
            continue
        pts = []
        for tok in el.text.replace("\n", " ").split():
            parts = tok.split(",")
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))  # lon, lat
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def project_to_metres(ring):
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    cos_lat = math.cos(math.radians(lat0))
    return [((lon - lon0) * EARTH_M_PER_DEG_LON * cos_lat,
             (lat - lat0) * EARTH_M_PER_DEG_LAT) for lon, lat in ring]


def plot_polygon_from_kml(data: bytes) -> Polygon:
    rings = parse_kml_rings(data)
    if not rings:
        raise ValueError("No polygon coordinates found in the KML file.")
    polys = []
    for ring in rings:
        poly = Polygon(project_to_metres(ring))
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.area > 0:
            polys.append(poly)
    if not polys:
        raise ValueError("Could not build a valid plot polygon from the KML.")
    return max(polys, key=lambda p: p.area)


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #
@dataclass
class MassingParams:
    setback: float = 3.0          # m, uniform
    floors: int = 8
    floor_height: float = 3.0     # m
    gap: float = 8.0              # m, MINIMUM separation between blocks
    coverage_cap: float = 50.0    # % of plot area
    veranda_pct: float = 25.0     # % covered-veranda allowance (of internal)
    mix: dict = field(default_factory=lambda: dict(DEFAULT_MIX))


# --------------------------------------------------------------------------- #
# Rectangular placement (clean floor plates, never slivers)
# --------------------------------------------------------------------------- #
def _inscribe_slabs(env: Polygon, depth: float, sep: float):
    """Largest set of rectangular slabs of `depth`, at the best orientation."""
    cen = (env.centroid.x, env.centroid.y)
    best = ([], 0, 0.0)
    for ang in range(0, 180, ANGLE_STEP):
        rot = affinity.rotate(env, -ang, origin=cen)
        rects = _bands(rot, depth, sep)
        area = sum(r.area for r in rects)
        if area > best[2]:
            best = (rects, ang, area)
    rects, ang, _ = best
    return [affinity.rotate(r, ang, origin=cen) for r in rects], ang


def _bands(rot_env: Polygon, depth: float, sep: float):
    """Inscribe an axis-aligned rectangle of `depth` in each horizontal band."""
    minx, miny, maxx, maxy = rot_env.bounds
    rects, y, step, N = [], miny, depth + sep, 20
    while y + depth <= maxy + 1e-6:
        lefts, rights, ok = [], [], True
        for k in range(N + 1):
            yy = y + depth * k / N
            seg = rot_env.intersection(LineString([(minx - 1, yy), (maxx + 1, yy)]))
            if seg.is_empty:
                ok = False
                break
            b = seg.bounds
            lefts.append(b[0])
            rights.append(b[2])
        if ok:
            left, right = max(lefts), min(rights)
            if right - left >= MIN_BUILDING_LEN:
                rects.append(box(left, y, right, y + depth))
        y += step
    return rects


def _pack_towers(env: Polygon, side: float, sep: float):
    """Pack square tower footprints fully inside the envelope, best orientation."""
    cen = (env.centroid.x, env.centroid.y)
    best = ([], 0)
    for ang in range(0, 180, ANGLE_STEP):
        rot = affinity.rotate(env, -ang, origin=cen)
        minx, miny, maxx, maxy = rot.bounds
        squares, y = [], miny
        while y + side <= maxy + 1e-6:
            x = minx
            while x + side <= maxx + 1e-6:
                sq = box(x, y, x + side, y + side)
                if rot.contains(sq):
                    squares.append(sq)
                x += side + sep
            y += side + sep
        if len(squares) > len(best[0]):
            best = (squares, ang)
    squares, ang = best
    return [affinity.rotate(s, ang, origin=cen) for s in squares], ang


# --------------------------------------------------------------------------- #
# Massing
# --------------------------------------------------------------------------- #
def _units_from_internal(internal: float, mix: dict) -> dict:
    total = sum(mix.values()) or 1
    return {name: int((internal * mix.get(name, 0) / total) // size)
            for name, size in UNIT_SIZES.items()}


def _evaluate(name, spec, env, p, sep, cap_area) -> dict:
    if spec["kind"] == "slab":
        blocks, angle = _inscribe_slabs(env, spec["depth"], sep)
    else:
        blocks, angle = _pack_towers(env, spec["side"], sep)

    # cap to coverage: keep largest blocks until the cap is hit
    blocks.sort(key=lambda b: b.area, reverse=True)
    kept, footprint = [], 0.0
    for b in blocks:
        if not kept or footprint + b.area <= cap_area:
            kept.append(b)
            footprint += b.area

    gfa = footprint * p.floors
    internal = gfa * spec["eff"]
    veranda = internal * (p.veranda_pct / 100.0)
    units = _units_from_internal(internal, p.mix)
    return {
        "typology": name, "blocks": kept, "angle": angle,
        "footprint": footprint, "gfa": gfa, "internal": internal,
        "veranda": veranda, "nsa": internal + veranda,
        "units": units, "total_units": sum(units.values()),
        "efficiency": round(spec["eff"] * 100),
    }


def compute_massing(kml_bytes: bytes, p: MassingParams) -> dict:
    plot = plot_polygon_from_kml(kml_bytes)
    envelope = plot.buffer(-p.setback, join_style=2)
    if envelope.is_empty or envelope.area <= 0:
        raise ValueError(
            f"Setback of {p.setback:g} m leaves no buildable area on this plot.")
    if envelope.geom_type == "MultiPolygon":
        envelope = max(envelope.geoms, key=lambda g: g.area)

    height = p.floors * p.floor_height
    sep = max(p.gap, 0.5 * height)          # daylight separation rule
    cap_area = plot.area * (p.coverage_cap / 100.0)

    options = [_evaluate(n, s, envelope, p, sep, cap_area)
               for n, s in TYPOLOGIES.items()]
    best = max(options, key=lambda o: (o["total_units"], o["nsa"]))

    return {
        "plot_area": round(plot.area),
        "envelope_area": round(envelope.area),
        "footprint": round(best["footprint"]),
        "coverage_pct": round(best["footprint"] / plot.area * 100, 1) if plot.area else 0,
        "orientation": best["angle"],
        "n_buildings": len(best["blocks"]),
        "floors": p.floors,
        "separation": round(sep, 1),
        "typology": best["typology"],
        "efficiency": best["efficiency"],
        "gfa": round(best["gfa"]),
        "internal": round(best["internal"]),
        "veranda": round(best["veranda"]),
        "nsa": round(best["nsa"]),
        "units": best["units"],
        "total_units": best["total_units"],
        "alternatives": [
            {"typology": o["typology"], "total_units": o["total_units"],
             "nsa": round(o["nsa"])}
            for o in options
        ],
        "svg": _build_svg(plot, envelope, best["blocks"]),
        "params": p,
    }


# --------------------------------------------------------------------------- #
# SVG site diagram
# --------------------------------------------------------------------------- #
def _build_svg(plot: Polygon, envelope: Polygon, blocks: list[Polygon]) -> str:
    minx, miny, maxx, maxy = plot.bounds
    w, h = maxx - minx, maxy - miny
    W, pad = 680.0, 24.0
    scale = (W - 2 * pad) / w if w else 1
    H = h * scale + 2 * pad

    def pts(poly: Polygon) -> str:
        return " ".join(
            f"{pad + (x - minx) * scale:.1f},{H - pad - (y - miny) * scale:.1f}"
            for x, y in poly.exterior.coords)

    def each(geom):
        return geom.geoms if geom.geom_type == "MultiPolygon" else [geom]

    parts = [
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;background:#F7FAFC;border-radius:12px;">']
    parts.append(f'<polygon points="{pts(plot)}" fill="#FFFFFF" '
                 f'stroke="#0A2536" stroke-width="2"/>')
    for g in each(envelope):
        parts.append(f'<polygon points="{pts(g)}" fill="#DAF6EF" fill-opacity="0.45" '
                     f'stroke="#5EA8A8" stroke-width="1.5" stroke-dasharray="6 4"/>')
    for b in blocks:
        parts.append(f'<polygon points="{pts(b)}" fill="#5EA8A8" fill-opacity="0.9" '
                     f'stroke="#0A2536" stroke-width="1.5"/>')
        # core marker (~6 m square at the block centroid)
        cx, cy = b.centroid.x, b.centroid.y
        core = box(cx - 3, cy - 3, cx + 3, cy + 3)
        parts.append(f'<polygon points="{pts(core)}" fill="#0A2536" fill-opacity="0.85"/>')
    # 10 m scale bar
    bar = 10 * scale
    y0 = H - 8
    parts.append(f'<line x1="{pad}" y1="{y0}" x2="{pad + bar}" y2="{y0}" '
                 f'stroke="#0A2536" stroke-width="2"/>')
    parts.append(f'<text x="{pad + bar + 6}" y="{y0 + 4}" font-family="sans-serif" '
                 f'font-size="11" fill="#6E8597">10 m</text>')
    parts.append("</svg>")
    return "".join(parts)
