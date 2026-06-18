"""
Allora brand system — single source of truth for colours, typography and
branded document/UI chrome.

This module is intentionally self-contained so it can be reused across Allora
tools (density calculator today, the DCF model tomorrow). It exposes:

  * Colour constants (hex + RGB) straight from the brand guidelines.
  * GIGA_SANS font registration for fpdf2.
  * AlloraPDF — an FPDF subclass that draws the branded header band and footer.
  * streamlit_brand_css() — a <style> block that themes a Streamlit app with the
    Giga Sans webfont and brand palette.

Brand reference: Allora Brand Guidelines v1.0 (Aug 2025).
"""

from __future__ import annotations

import base64
from pathlib import Path

from fpdf import FPDF

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
LOGOS_DIR = ASSETS_DIR / "logos"

LOGO_DARK = LOGOS_DIR / "allora_logo_dark.png"    # two-colour mark for light bg
LOGO_WHITE = LOGOS_DIR / "allora_logo_white.png"  # reversed mark for dark bg
SYMBOL_WHITE = LOGOS_DIR / "allora_symbol_white.png"

# --------------------------------------------------------------------------- #
# Brand colours  (Allora Brand Guidelines, pp. 12-14)
# --------------------------------------------------------------------------- #
# Primary palette
NOXEN = "#0A2536"     # authority, trust, stability — primary dark
NAVARIS = "#33566D"   # innovation, reliability — mid blue
NIVELLE = "#F3FAFF"   # clarity, neutrality — near white
# Secondary palette
CYMARIS = "#5EA8A8"   # the keyhole teal — primary accent
CLARIA = "#DAF6EF"    # light mint — soft fill

# Functional neutrals derived from the palette (kept on-brand)
INK = NOXEN           # body text on light
MUTED = "#6E8597"     # captions / secondary text (a desaturated Navaris)
HAIRLINE = "#D7E0E6"  # subtle dividers

URL = "https://allora.capital"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """'#0A2536' -> (10, 37, 54)."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Typography — Giga Sans (primary brand typeface)
# --------------------------------------------------------------------------- #
GIGA = "Giga"  # family name used after registration

_GIGA_WEIGHTS = {
    "": "GigaSans-Regular.otf",
    "B": "GigaSans-Bold.otf",
    # fpdf2 only keys off "", "B", "I", "BI" — expose the extra weights via
    # GIGA_SEMIBOLD / GIGA_MEDIUM / GIGA_LIGHT families for finer control.
}
GIGA_SEMIBOLD = "GigaSB"
GIGA_MEDIUM = "GigaMed"
GIGA_LIGHT = "GigaLight"


def register_fonts(pdf: FPDF) -> None:
    """Register every Giga Sans weight we ship as fpdf2 font families."""
    pdf.add_font(GIGA, "", str(FONTS_DIR / "GigaSans-Regular.otf"))
    pdf.add_font(GIGA, "B", str(FONTS_DIR / "GigaSans-Bold.otf"))
    pdf.add_font(GIGA_SEMIBOLD, "", str(FONTS_DIR / "GigaSans-SemiBold.otf"))
    pdf.add_font(GIGA_MEDIUM, "", str(FONTS_DIR / "GigaSans-Medium.otf"))
    pdf.add_font(GIGA_LIGHT, "", str(FONTS_DIR / "GigaSans-Light.otf"))


# --------------------------------------------------------------------------- #
# Branded PDF base class
# --------------------------------------------------------------------------- #
class AlloraPDF(FPDF):
    """
    FPDF subclass that paints the Allora header band and footer on every page.

    Usage:
        pdf = AlloraPDF(title="Density Analysis", category="Land Feasibility")
        pdf.add_page()
        pdf.body_heading("Summary")
        ...
    """

    BAND_H = 30  # header band height (mm)
    MARGIN = 15

    def __init__(self, title: str = "", category: str = "", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.category_text = category
        self.set_margins(self.MARGIN, self.BAND_H + 12, self.MARGIN)
        self.set_auto_page_break(auto=True, margin=22)
        register_fonts(self)
        self.set_text_color(*hex_to_rgb(INK))

    # -- chrome ----------------------------------------------------------- #
    def header(self) -> None:
        # Noxen band across the full page width
        self.set_fill_color(*hex_to_rgb(NOXEN))
        self.rect(0, 0, self.w, self.BAND_H, style="F")

        # Reversed wordmark, left
        logo_h = 11
        if LOGO_WHITE.exists():
            self.image(str(LOGO_WHITE), x=self.MARGIN, y=(self.BAND_H - logo_h) / 2,
                       h=logo_h)

        # Category + title, right aligned
        right = self.w - self.MARGIN
        if self.category_text:
            self.set_xy(self.w / 2, 8)
            self.set_font(GIGA_MEDIUM, "", 8)
            self.set_text_color(*hex_to_rgb(CYMARIS))
            self.cell(right - self.w / 2, 5, self._track(self.category_text.upper()),
                      align="R")
        if self.title_text:
            self.set_xy(self.w / 2, 13)
            self.set_font(GIGA, "B", 17)
            self.set_text_color(255, 255, 255)
            self.cell(right - self.w / 2, 10, self.title_text, align="R")

        # Cymaris accent rule along the bottom of the band
        self.set_draw_color(*hex_to_rgb(CYMARIS))
        self.set_line_width(0.8)
        self.line(0, self.BAND_H, self.w, self.BAND_H)

        # reset for body
        self.set_text_color(*hex_to_rgb(INK))
        self.set_line_width(0.2)

    def footer(self) -> None:
        self.set_y(-17)
        # hairline above footer
        self.set_draw_color(*hex_to_rgb(HAIRLINE))
        self.set_line_width(0.3)
        self.line(self.MARGIN, self.get_y(), self.w - self.MARGIN, self.get_y())
        self.ln(2)

        # dark wordmark, left
        if LOGO_DARK.exists():
            self.image(str(LOGO_DARK), x=self.MARGIN, y=self.get_y() + 0.5, h=6)

        # url, centre
        self.set_font(GIGA, "", 7.5)
        self.set_text_color(*hex_to_rgb(MUTED))
        self.set_y(-13)
        self.cell(0, 5, URL, align="C")

        # page number, right
        self.set_xy(self.w - self.MARGIN - 30, -13)
        self.set_text_color(*hex_to_rgb(NAVARIS))
        self.cell(30, 5, str(self.page_no()), align="R")
        self.set_text_color(*hex_to_rgb(INK))

    # -- body helpers ----------------------------------------------------- #
    def body_heading(self, text: str) -> None:
        """Section heading: Giga Bold in Noxen with a short Cymaris underline."""
        self.ln(2)
        self.set_font(GIGA, "B", 13)
        self.set_text_color(*hex_to_rgb(NOXEN))
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        y = self.get_y()
        self.set_draw_color(*hex_to_rgb(CYMARIS))
        self.set_line_width(0.8)
        self.line(self.MARGIN, y, self.MARGIN + 18, y)
        self.set_line_width(0.2)
        self.ln(3)

    @staticmethod
    def _track(text: str, spaces: int = 1) -> str:
        """Cheap letter-spacing for small caps labels."""
        return (" " * spaces).join(list(text))


# --------------------------------------------------------------------------- #
# Streamlit theming
# --------------------------------------------------------------------------- #
def _font_face(family: str, file: str, weight: int) -> str:
    data = base64.b64encode((FONTS_DIR / file).read_bytes()).decode()
    return (
        f"@font-face{{font-family:'{family}';font-style:normal;"
        f"font-weight:{weight};src:url(data:font/otf;base64,{data}) "
        f"format('opentype');}}"
    )


def streamlit_brand_css() -> str:
    """A <style> block: embeds Giga Sans and themes Streamlit with the palette."""
    faces = "".join([
        _font_face("Giga Sans", "GigaSans-Light.otf", 300),
        _font_face("Giga Sans", "GigaSans-Regular.otf", 400),
        _font_face("Giga Sans", "GigaSans-Medium.otf", 500),
        _font_face("Giga Sans", "GigaSans-SemiBold.otf", 600),
        _font_face("Giga Sans", "GigaSans-Bold.otf", 700),
    ])
    return f"""
<style>
{faces}
:root {{
  --noxen:{NOXEN}; --navaris:{NAVARIS}; --nivelle:{NIVELLE};
  --cymaris:{CYMARIS}; --claria:{CLARIA}; --muted:{MUTED};
}}
html, body, [class*="css"], .stApp, .stMarkdown, p, div, span, label, input,
button, h1, h2, h3, h4, h5, h6 {{
  font-family:'Giga Sans', -apple-system, sans-serif !important;
}}
/* Keep Material icon glyphs on their icon font (the rule above would otherwise
   turn ligatures like "keyboard_double_arrow_right" into literal text). */
[data-testid="stIconMaterial"], .material-icons, .material-icons-outlined,
.material-symbols-outlined, .material-symbols-rounded, span[translate="no"],
.stApp i {{
  font-family:'Material Symbols Rounded','Material Symbols Outlined',
              'Material Icons' !important;
}}
.stApp {{ background:#FFFFFF; }}
h1, h2, h3 {{ color:var(--noxen) !important; font-weight:700 !important; }}
/* Top decoration bar -> brand gradient */
[data-testid="stDecoration"] {{
  background-image:linear-gradient(90deg, var(--noxen), var(--cymaris)) !important;
}}
/* Radio / checkbox / slider accents come from primaryColor in
   .streamlit/config.toml (Cymaris) — more reliable than CSS overrides. */
/* Sidebar -> Noxen panel */
section[data-testid="stSidebar"] {{ background:var(--noxen); }}
section[data-testid="stSidebar"] * {{ color:var(--nivelle) !important; }}
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stNumberInput input {{
  color:var(--noxen) !important; background:var(--nivelle) !important;
}}
/* Number-input +/- steppers: make them clearly visible (Cymaris + white glyph)
   instead of the faint default that blends into the input fill. */
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {{
  background:var(--cymaris) !important; border:none !important;
  color:#fff !important; opacity:1 !important; width:2.2rem;
}}
[data-testid="stNumberInputStepUp"]:hover,
[data-testid="stNumberInputStepDown"]:hover {{
  background:var(--navaris) !important;
}}
[data-testid="stNumberInputStepUp"] *, [data-testid="stNumberInputStepDown"] * {{
  color:#fff !important; fill:#fff !important;
}}
/* Primary buttons -> Cymaris */
.stButton>button, .stDownloadButton>button {{
  background:var(--cymaris); color:#fff; border:none; border-radius:6px;
  font-weight:600; padding:0.5rem 1.4rem;
}}
.stButton>button:hover, .stDownloadButton>button:hover {{
  background:var(--navaris); color:#fff;
}}
.stButton>button:focus, .stButton>button:active, .stButton>button:focus-visible,
.stDownloadButton>button:focus, .stDownloadButton>button:active,
.stDownloadButton>button:focus-visible {{
  background:var(--navaris) !important; color:#fff !important;
  border:none !important; box-shadow:none !important; outline:none !important;
}}
/* Brand stat card */
.allora-kpi {{
  border-radius:10px; padding:16px 18px; margin-bottom:12px; color:#fff;
}}
.allora-kpi .label {{ font-size:0.72rem; letter-spacing:.08em;
  text-transform:uppercase; opacity:.85; font-weight:600; }}
.allora-kpi .value {{ font-size:1.55rem; font-weight:700; line-height:1.2; }}
.allora-kpi .detail {{ font-size:0.85rem; opacity:.9; margin-top:4px; }}
.kpi-noxen   {{ background:var(--noxen); }}
.kpi-cymaris {{ background:var(--cymaris); }}
.kpi-navaris {{ background:var(--navaris); }}
.kpi-claria  {{ background:var(--claria); color:var(--noxen); }}
.kpi-claria .label {{ opacity:.7; }}
</style>
"""
