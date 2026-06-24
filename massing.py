"""
Site massing — import a plot KML and propose a realistic apartment masterplan.

v4 (apartments only): places rectangular floor plates inside the buildable
envelope, then *optimises the unit combination for one typical floor* —
favouring 2-bed and capping 1-bed — and tiles that recommended mix as individual
apartment modules + a core, colour-coded by type. Picks the typology that fits
best, shows a legend, and draws road access on the chosen compass side(s) with a
north arrow (true north from the KML).

Parking is assumed in basement under the building and is not modelled spatially.
Indicative feasibility massing only — flat-polygon model, ignores topography.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import LineString, Polygon, box

# Apartment unit catalogue (internal areas, m²)
UNIT_SIZES = {"1-bed": 50.0, "2-bed": 82.0, "3-bed": 110.0}

# Palette (brand)
UNIT_COLORS = {"1-bed": "#DAF6EF", "2-bed": "#5EA8A8", "3-bed": "#33566D"}
CORE_COLOR = "#0A2536"
ROAD_COLOR = "#9AA8B2"

# Typology geometry (metres)
TYPOLOGIES = {
    "Double-loaded slab":    {"kind": "slab",    "depth": 21.0},
    "Single-loaded gallery": {"kind": "gallery", "depth": 12.0},
    "Point towers":          {"kind": "tower",   "side": 24.0},
}
CORRIDOR = 1.5
CORE_LEN = 7.0
TOWER_CORE = 8.0
TOWER_RING = 8.0
MIN_BUILDING_LEN = 16.0
ANGLE_STEP = 5

EARTH_M_PER_DEG_LAT = 110_540.0
EARTH_M_PER_DEG_LON = 111_320.0
SIDE_VECTORS = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}


# --------------------------------------------------------------------------- #
# KML parsing + projection
# --------------------------------------------------------------------------- #
def parse_kml_rings(data: bytes):
    root = ET.fromstring(data)
    rings = []
    for el in root.iter():
        if not el.tag.endswith("coordinates") or not (el.text and el.text.strip()):
            continue
        pts = []
        for tok in el.text.replace("\n", " ").split():
            parts = tok.split(",")
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))
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
    setback: float = 3.0
    floors: int = 8
    floor_height: float = 3.0
    gap: float = 8.0
    coverage_cap: float = 50.0
    veranda_pct: float = 25.0
    min_2bed_pct: float = 50.0     # favour 2-bed: at least this share
    max_1bed_pct: float = 30.0     # cap on 1-bed share
    road_sides: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Rectangular placement (frames in rotated frame + angle back to global)
# --------------------------------------------------------------------------- #
def _inscribe_slabs(env, depth, sep, origin):
    best = ([], 0, 0.0)
    for ang in range(0, 180, ANGLE_STEP):
        rot = affinity.rotate(env, -ang, origin=origin)
        frames = _bands(rot, depth, sep)
        area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in frames)
        if area > best[2]:
            best = (frames, ang, area)
    return best[0], best[1]


def _bands(rot_env, depth, sep):
    minx, miny, maxx, maxy = rot_env.bounds
    frames, y, step, N = [], miny, depth + sep, 20
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
        if ok and min(rights) - max(lefts) >= MIN_BUILDING_LEN:
            frames.append((max(lefts), y, min(rights), y + depth))
        y += step
    return frames


def _pack_towers(env, side, sep, origin):
    best = ([], 0)
    for ang in range(0, 180, ANGLE_STEP):
        rot = affinity.rotate(env, -ang, origin=origin)
        minx, miny, maxx, maxy = rot.bounds
        frames, y = [], miny
        while y + side <= maxy + 1e-6:
            x = minx
            while x + side <= maxx + 1e-6:
                if rot.contains(box(x, y, x + side, y + side)):
                    frames.append((x, y, x + side, y + side))
                x += side + sep
            y += side + sep
        if len(frames) > len(best[0]):
            best = (frames, ang)
    return best[0], best[1]


# --------------------------------------------------------------------------- #
# Rows of a floor plate (where units go), and the one-floor optimiser
# --------------------------------------------------------------------------- #
def _rows_for_frame(frame, kind, core_at_x1):
    """Return (core_boxes, rows, depth). row = (ax, ay, length, depth, horiz)."""
    x0, y0, x1, y1 = frame
    if kind == "tower":
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        core = box(cx - TOWER_CORE / 2, cy - TOWER_CORE / 2,
                   cx + TOWER_CORE / 2, cy + TOWER_CORE / 2)
        ud = TOWER_RING
        rows = [
            (x0, y0, x1 - x0, ud, True),                 # bottom
            (x0, y1 - ud, x1 - x0, ud, True),            # top
        ]
        mid = (y1 - ud) - (y0 + ud)
        if mid > 0:
            rows.append((x0, y0 + ud, mid, ud, False))   # left  (vertical)
            rows.append((x1 - ud, y0 + ud, mid, ud, False))  # right (vertical)
        return [core], rows, ud

    # slab / gallery
    D = y1 - y0
    if core_at_x1:
        core = box(x1 - CORE_LEN, y0, x1, y1)
        ux0, ulen = x0, (x1 - CORE_LEN) - x0
    else:
        core = box(x0, y0, x0 + CORE_LEN, y1)
        ux0, ulen = x0 + CORE_LEN, x1 - (x0 + CORE_LEN)
    if kind == "slab":
        ud = (D - CORRIDOR) / 2
        rows = [(ux0, y0, ulen, ud, True), (ux0, y1 - ud, ulen, ud, True)]
    else:  # gallery
        ud = max(D - CORRIDOR, 1.0)
        rows = [(ux0, y0, ulen, ud, True)]
    return [core], rows, ud


def _optimize_floor(frontage, depth, min2, max1):
    """Best (n1, n2, n3) for one floor: most units with 2-bed favoured, 1-bed capped."""
    f = {t: UNIT_SIZES[t] / depth for t in UNIT_SIZES}
    f1, f2, f3 = f["1-bed"], f["2-bed"], f["3-bed"]

    def solve(req_min2, req_max1):
        best = None
        for n1 in range(int(frontage // f1) + 1):
            r1 = frontage - n1 * f1
            if r1 < 0:
                break
            for n2 in range(int(r1 // f2) + 1):
                r2 = r1 - n2 * f2
                n3 = int(r2 // f3)
                total = n1 + n2 + n3
                if total == 0:
                    continue
                if n1 > req_max1 / 100 * total + 1e-9:
                    continue
                if n2 < req_min2 / 100 * total - 1e-9:
                    continue
                used = n1 * f1 + n2 * f2 + n3 * f3
                score = (total, used, n2)
                if best is None or score > best[0]:
                    best = (score, (n1, n2, n3))
        return best[1] if best else None

    # try full constraints, then relax min-2-bed, then the 1-bed cap
    return solve(min2, max1) or solve(0, max1) or solve(0, 100) or (0, 0, 0)


def _queue(counts):
    order, rem, q = ["2-bed", "3-bed", "1-bed"], dict(counts), []
    while sum(rem.values()) > 0:
        for t in order:
            if rem[t] > 0:
                q.append(t)
                rem[t] -= 1
    return q


def _place(rows, depth, queue):
    """Greedily place queued units into rows; return (cells, placed_counts)."""
    fronts = {t: UNIT_SIZES[t] / depth for t in UNIT_SIZES}
    cells, placed = [], {t: 0 for t in UNIT_SIZES}
    q = list(queue)
    for ax, ay, length, d, horiz in rows:
        off = 0.0
        while q:
            remaining = length - off
            idx = next((i for i, t in enumerate(q) if fronts[t] <= remaining + 1e-6), None)
            if idx is None:
                break
            t = q.pop(idx)
            fr = fronts[t]
            if horiz:
                cells.append((box(ax + off, ay, ax + off + fr, ay + d), t))
            else:
                cells.append((box(ax, ay + off, ax + d, ay + off + fr), t))
            off += fr
            placed[t] += 1
    return cells, placed


# --------------------------------------------------------------------------- #
# Evaluate one typology
# --------------------------------------------------------------------------- #
def _rot_vec(vx, vy, deg):
    r = math.radians(deg)
    return (vx * math.cos(r) - vy * math.sin(r), vx * math.sin(r) + vy * math.cos(r))


def _evaluate(name, spec, env, p, sep, cap_area, origin, road_vec):
    kind = spec["kind"]
    if kind == "tower":
        frames, angle = _pack_towers(env, spec["side"], sep, origin)
    else:
        frames, angle = _inscribe_slabs(env, spec["depth"], sep, origin)

    frames.sort(key=lambda f: (f[2] - f[0]) * (f[3] - f[1]), reverse=True)
    kept, footprint = [], 0.0
    for f in frames:
        a = (f[2] - f[0]) * (f[3] - f[1])
        if not kept or footprint + a <= cap_area:
            kept.append(f)
            footprint += a

    rl = _rot_vec(road_vec[0], road_vec[1], -angle)
    core_at_x1 = rl[0] > 0.01

    # collect rows + cores across all buildings; depth is typology-consistent
    cores, all_rows, depth = [], [], None
    for f in kept:
        c, rows, depth = _rows_for_frame(f, kind, core_at_x1)
        cores += c
        all_rows += rows
    if depth is None or not all_rows:
        return {"typology": name, "angle": angle, "footprint": footprint,
                "cells_global": [], "frames_global": [], "gfa": 0, "internal": 0,
                "veranda": 0, "nsa": 0, "units": {t: 0 for t in UNIT_SIZES},
                "total_units": 0, "floor_units": {t: 0 for t in UNIT_SIZES},
                "floor_total": 0, "efficiency": 0}

    # Budget = usable frontage minus a per-row slack (< one 1-bed) so that every
    # optimised unit actually fits during placement and the recommended mix holds.
    frontage = sum(r[2] for r in all_rows)
    budget = max(0.0, frontage - len(all_rows) * (UNIT_SIZES["1-bed"] / depth))
    n1, n2, n3 = _optimize_floor(budget, depth, p.min_2bed_pct, p.max_1bed_pct)
    cells, floor_counts = _place(all_rows, depth, _queue(
        {"1-bed": n1, "2-bed": n2, "3-bed": n3}))

    # to global coords
    cells_global = [(affinity.rotate(g, angle, origin=origin), t) for g, t in cells]
    for c in cores:
        cells_global.append((affinity.rotate(c, angle, origin=origin), "core"))
    frames_global = [affinity.rotate(box(*f), angle, origin=origin) for f in kept]

    floor_total = sum(floor_counts.values())
    internal_floor = sum(UNIT_SIZES[t] * floor_counts[t] for t in UNIT_SIZES)
    internal = internal_floor * p.floors
    veranda = internal * (p.veranda_pct / 100.0)
    units = {t: floor_counts[t] * p.floors for t in UNIT_SIZES}
    gfa = footprint * p.floors
    return {
        "typology": name, "angle": angle, "footprint": footprint,
        "cells_global": cells_global, "frames_global": frames_global,
        "gfa": gfa, "internal": internal, "veranda": veranda,
        "nsa": internal + veranda, "units": units,
        "total_units": sum(units.values()),
        "floor_units": floor_counts, "floor_total": floor_total,
        "efficiency": round(internal / gfa * 100) if gfa else 0,
    }


def compute_massing(kml_bytes: bytes, p: MassingParams) -> dict:
    plot = plot_polygon_from_kml(kml_bytes)
    envelope = plot.buffer(-p.setback, join_style=2)
    if envelope.is_empty or envelope.area <= 0:
        raise ValueError(
            f"Setback of {p.setback:g} m leaves no buildable area on this plot.")
    if envelope.geom_type == "MultiPolygon":
        envelope = max(envelope.geoms, key=lambda g: g.area)

    origin = (envelope.centroid.x, envelope.centroid.y)
    sep = max(p.gap, 0.5 * p.floors * p.floor_height)
    cap_area = plot.area * (p.coverage_cap / 100.0)

    road_vec = (0.0, 0.0)
    for s in p.road_sides:
        v = SIDE_VECTORS.get(s)
        if v:
            road_vec = (road_vec[0] + v[0], road_vec[1] + v[1])

    options = [_evaluate(n, s, envelope, p, sep, cap_area, origin, road_vec)
               for n, s in TYPOLOGIES.items()]
    best = max(options, key=lambda o: (o["total_units"], o["nsa"]))

    return {
        "plot_area": round(plot.area),
        "envelope_area": round(envelope.area),
        "footprint": round(best["footprint"]),
        "coverage_pct": round(best["footprint"] / plot.area * 100, 1) if plot.area else 0,
        "orientation": best["angle"],
        "n_buildings": len(best["frames_global"]),
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
        "floor_units": best["floor_units"],
        "floor_total": best["floor_total"],
        "alternatives": [
            {"typology": o["typology"], "total_units": o["total_units"],
             "nsa": round(o["nsa"])} for o in options],
        "road_sides": p.road_sides,
        "colors": {**UNIT_COLORS, "core": CORE_COLOR, "road": ROAD_COLOR},
        "svg": _build_svg(plot, envelope, best["cells_global"],
                          best["frames_global"], p.road_sides),
        "params": p,
    }


# --------------------------------------------------------------------------- #
# SVG site diagram
# --------------------------------------------------------------------------- #
def _build_svg(plot, envelope, cells, frames, road_sides) -> str:
    minx, miny, maxx, maxy = plot.bounds
    road_w = 8.0
    roads = []
    for s in road_sides:
        if s == "N":
            roads.append((box(minx, maxy, maxx, maxy + road_w), s, (minx + maxx) / 2, maxy + road_w / 2))
        elif s == "S":
            roads.append((box(minx, miny - road_w, maxx, miny), s, (minx + maxx) / 2, miny - road_w / 2))
        elif s == "E":
            roads.append((box(maxx, miny, maxx + road_w, maxy), s, maxx + road_w / 2, (miny + maxy) / 2))
        elif s == "W":
            roads.append((box(minx - road_w, miny, minx, maxy), s, minx - road_w / 2, (miny + maxy) / 2))

    bx0 = min([minx] + [r[0].bounds[0] for r in roads])
    by0 = min([miny] + [r[0].bounds[1] for r in roads])
    bx1 = max([maxx] + [r[0].bounds[2] for r in roads])
    by1 = max([maxy] + [r[0].bounds[3] for r in roads])
    w, h = bx1 - bx0, by1 - by0
    W, pad = 680.0, 28.0
    scale = (W - 2 * pad) / w if w else 1
    H = h * scale + 2 * pad

    def P(x, y):
        return f"{pad + (x - bx0) * scale:.1f},{H - pad - (y - by0) * scale:.1f}"

    def poly(g, fill, stroke, sw, dash="", op=1.0):
        pts = " ".join(P(x, y) for x, y in g.exterior.coords)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<polygon points="{pts}" fill="{fill}" fill-opacity="{op}" '
                f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    parts = [f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;background:#F7FAFC;border-radius:12px;">']
    for g, s, lx, ly in roads:
        parts.append(poly(g, ROAD_COLOR, ROAD_COLOR, 0))
        px = P(lx, ly).split(",")
        parts.append(f'<text x="{px[0]}" y="{px[1]}" font-family="sans-serif" '
                     f'font-size="11" font-weight="700" fill="#fff" text-anchor="middle" '
                     f'dominant-baseline="middle">ROAD ({s})</text>')
    parts.append(poly(plot, "#FFFFFF", "#0A2536", 2))
    for g in (envelope.geoms if envelope.geom_type == "MultiPolygon" else [envelope]):
        parts.append(poly(g, "#DAF6EF", "#5EA8A8", 1.2, dash="6 4", op=0.35))
    for f in frames:
        parts.append(poly(f, "none", "#0A2536", 1.6))
    for g, t in cells:
        fill = CORE_COLOR if t == "core" else UNIT_COLORS.get(t, "#999")
        parts.append(poly(g, fill, "#FFFFFF", 0.6, op=0.95))
    nx, ny = W - 22, 16
    parts.append(f'<line x1="{nx}" y1="{ny + 26}" x2="{nx}" y2="{ny}" stroke="#0A2536" stroke-width="2"/>')
    parts.append(f'<polygon points="{nx - 4},{ny + 5} {nx + 4},{ny + 5} {nx},{ny - 3}" fill="#0A2536"/>')
    parts.append(f'<text x="{nx}" y="{ny + 38}" font-family="sans-serif" font-size="11" '
                 f'font-weight="700" fill="#0A2536" text-anchor="middle">N</text>')
    bar = 10 * scale
    y0 = H - 8
    parts.append(f'<line x1="{pad}" y1="{y0}" x2="{pad + bar}" y2="{y0}" stroke="#0A2536" stroke-width="2"/>')
    parts.append(f'<text x="{pad + bar + 6}" y="{y0 + 4}" font-family="sans-serif" '
                 f'font-size="11" fill="#6E8597">10 m</text>')
    parts.append("</svg>")
    return "".join(parts)
