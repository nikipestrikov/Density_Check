"""
Site massing — import a plot KML and propose an optimal apartment building shape.

v1 scope (apartments / highrise only):
  * Parse the plot boundary from a KML.
  * Project lat/long to metres (local equirectangular — accurate at plot scale).
  * Apply a uniform setback -> buildable envelope.
  * Lay out apartment "bars" of a daylight depth, separated for light, at the
    orientation that maximises floor plate, capped by the coverage limit.
  * Estimate GFA / internal NSA / covered verandas / unit mix.
  * Render an SVG site diagram.

Indicative feasibility massing only — flat-polygon model, ignores topography.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

# Fixed unit catalogue (internal areas, m²) — apartments
UNIT_SIZES = {"1-bed": 50.0, "2-bed": 82.0, "3-bed": 110.0}
DEFAULT_MIX = {"1-bed": 30, "2-bed": 45, "3-bed": 25}  # percent

EARTH_M_PER_DEG_LAT = 110_540.0
EARTH_M_PER_DEG_LON = 111_320.0


# --------------------------------------------------------------------------- #
# KML parsing + projection
# --------------------------------------------------------------------------- #
def parse_kml_rings(data: bytes) -> list[list[tuple[float, float]]]:
    """Return every coordinate ring (lon, lat) found in a KML."""
    root = ET.fromstring(data)
    rings: list[list[tuple[float, float]]] = []
    for el in root.iter():
        if not el.tag.endswith("coordinates") or not (el.text and el.text.strip()):
            continue
        pts: list[tuple[float, float]] = []
        for tok in el.text.replace("\n", " ").split():
            parts = tok.split(",")
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))  # lon, lat
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def project_to_metres(ring: list[tuple[float, float]]):
    """Local equirectangular projection centred on the ring centroid."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    cos_lat = math.cos(math.radians(lat0))
    return [
        ((lon - lon0) * EARTH_M_PER_DEG_LON * cos_lat,
         (lat - lat0) * EARTH_M_PER_DEG_LAT)
        for lon, lat in ring
    ]


def plot_polygon_from_kml(data: bytes) -> Polygon:
    """Largest valid polygon (in metres) from a KML."""
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
# Massing
# --------------------------------------------------------------------------- #
@dataclass
class MassingParams:
    setback: float = 3.0          # m, uniform
    depth: float = 14.0           # m, building (bar) depth for daylight
    gap: float = 16.0             # m, separation between bars
    floors: int = 8
    coverage_cap: float = 50.0    # % of plot area
    efficiency: float = 82.0      # % net internal / GFA
    veranda_pct: float = 25.0     # % covered veranda allowance (of internal)
    mix: dict = field(default_factory=lambda: dict(DEFAULT_MIX))


def _bars_at_angle(envelope: Polygon, angle: float, depth: float, gap: float):
    """Tile the envelope with horizontal bars at a rotation, return bar polys."""
    cx, cy = envelope.centroid.x, envelope.centroid.y
    rot = affinity.rotate(envelope, -angle, origin=(cx, cy))
    minx, miny, maxx, maxy = rot.bounds
    bars = []
    y = miny
    step = depth + gap
    # guard against pathological inputs
    if step <= 0:
        return []
    while y < maxy:
        strip = box(minx - 1, y, maxx + 1, y + depth)
        piece = rot.intersection(strip)
        if not piece.is_empty and piece.area > 0:
            bars.append(piece)
        y += step
    # rotate bars back to real orientation
    return [affinity.rotate(b, angle, origin=(cx, cy)) for b in bars]


def compute_massing(kml_bytes: bytes, p: MassingParams) -> dict:
    plot = plot_polygon_from_kml(kml_bytes)
    plot_area = plot.area

    envelope = plot.buffer(-p.setback, join_style=2)  # mitre
    if envelope.is_empty or envelope.area <= 0:
        raise ValueError(
            f"Setback of {p.setback:g} m leaves no buildable area on this plot.")
    # buffer can return a MultiPolygon; keep the largest piece
    if envelope.geom_type == "MultiPolygon":
        envelope = max(envelope.geoms, key=lambda g: g.area)

    coverage_cap_area = plot_area * (p.coverage_cap / 100.0)

    # Search orientation (0–179°) for the layout with the most floor plate
    best_bars, best_area = [], -1.0
    for angle in range(0, 180, 2):
        bars = _bars_at_angle(envelope, angle, p.depth, p.gap)
        area = sum(b.area for b in bars)
        if area > best_area:
            best_area, best_bars, best_angle = area, bars, angle

    # Trim outermost bars if coverage cap is exceeded
    best_bars.sort(key=lambda b: b.area, reverse=True)
    footprint = 0.0
    kept = []
    for b in best_bars:
        if footprint + b.area <= coverage_cap_area or not kept:
            kept.append(b)
            footprint += b.area
    bars = kept
    footprint = sum(b.area for b in bars)

    gfa = footprint * p.floors
    internal = gfa * (p.efficiency / 100.0)
    veranda = internal * (p.veranda_pct / 100.0)
    nsa = internal + veranda

    # Unit mix — allocate internal area by the requested split
    mix_total = sum(p.mix.values()) or 1
    units = {}
    for name, size in UNIT_SIZES.items():
        share = p.mix.get(name, 0) / mix_total
        units[name] = int((internal * share) // size)
    total_units = sum(units.values())

    return {
        "plot_area": round(plot_area),
        "envelope_area": round(envelope.area),
        "footprint": round(footprint),
        "coverage_pct": round(footprint / plot_area * 100, 1) if plot_area else 0,
        "orientation": best_angle,
        "n_bars": len(bars),
        "floors": p.floors,
        "gfa": round(gfa),
        "internal": round(internal),
        "veranda": round(veranda),
        "nsa": round(nsa),
        "units": units,
        "total_units": total_units,
        "svg": _build_svg(plot, envelope, bars),
        "params": p,
    }


# --------------------------------------------------------------------------- #
# SVG site diagram
# --------------------------------------------------------------------------- #
def _build_svg(plot: Polygon, envelope: Polygon, bars: list[Polygon]) -> str:
    minx, miny, maxx, maxy = plot.bounds
    w, h = maxx - minx, maxy - miny
    W = 680.0
    pad = 24.0
    scale = (W - 2 * pad) / w if w else 1
    H = h * scale + 2 * pad

    def pts(poly: Polygon) -> str:
        return " ".join(
            f"{pad + (x - minx) * scale:.1f},{H - pad - (y - miny) * scale:.1f}"
            for x, y in poly.exterior.coords
        )

    def polys(geom):
        geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        return [g for g in geoms if not g.is_empty]

    parts = [
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;background:#F7FAFC;border-radius:12px;">'
    ]
    # plot
    parts.append(f'<polygon points="{pts(plot)}" fill="#FFFFFF" '
                 f'stroke="#0A2536" stroke-width="2"/>')
    # buildable envelope (dashed)
    for g in polys(envelope):
        parts.append(f'<polygon points="{pts(g)}" fill="#DAF6EF" fill-opacity="0.5" '
                     f'stroke="#5EA8A8" stroke-width="1.5" stroke-dasharray="6 4"/>')
    # apartment bars
    for b in bars:
        for g in polys(b):
            parts.append(f'<polygon points="{pts(g)}" fill="#5EA8A8" '
                         f'fill-opacity="0.85" stroke="#0A2536" stroke-width="1"/>')
    # scale bar (10 m)
    bar_px = 10 * scale
    y0 = H - 8
    parts.append(f'<line x1="{pad}" y1="{y0}" x2="{pad + bar_px}" y2="{y0}" '
                 f'stroke="#0A2536" stroke-width="2"/>')
    parts.append(f'<text x="{pad + bar_px + 6}" y="{y0 + 4}" '
                 f'font-family="sans-serif" font-size="11" fill="#6E8597">10 m</text>')
    parts.append("</svg>")
    return "".join(parts)
