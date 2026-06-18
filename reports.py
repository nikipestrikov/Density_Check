"""Report generators (PDF + Excel) styled with the Allora brand system."""

from io import BytesIO

import pandas as pd

from branding import (
    AlloraPDF, GIGA, GIGA_MEDIUM, GIGA_SEMIBOLD,
    NOXEN, NAVARIS, CYMARIS, CLARIA, NIVELLE, MUTED, hex_to_rgb,
)


# ----------------------- PDF Report Generator -----------------------#
def generate_pdf_report(results, total_price, price_per_m2, project_name):
    pdf = AlloraPDF(title="Density Analysis", category="Land Feasibility",
                    orientation="P", unit="mm", format="A4")
    pdf.add_page()

    # ---- Project + headline price ------------------------------------- #
    pdf.set_font(GIGA, "B", 18)
    pdf.set_text_color(*hex_to_rgb(NOXEN))
    pdf.cell(0, 10, project_name, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(GIGA_MEDIUM, "", 10)
    pdf.set_text_color(*hex_to_rgb(MUTED))
    pdf.cell(0, 6, "Buildable density & land-value summary",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Headline KPI band (Cymaris) — total price
    _kpi_banner(pdf, "Total Project Price", f"EUR {total_price:,.0f}")
    pdf.ln(6)

    # ---- Summary stat cards ------------------------------------------- #
    pdf.body_heading("Summary")
    deductions = results["total_road_deduction"] + results["total_green_deduction"]
    cards = [
        ("Total Buildable Area", f"{round(results['total_buildable_area']):,} m²"),
        ("Residential", f"{round(results['residential_buildable_area']):,} m²"),
        ("Commercial", f"{round(results['commercial_buildable_area']):,} m²"),
        ("Total Deductions", f"{round(deductions):,} m²"),
        ("Coverage Area", f"{round(results.get('total_coverage_area', 0)):,} m²"),
        ("Price / Buildable m²", f"EUR {round(price_per_m2):,}"),
    ]
    _stat_cards(pdf, cards, per_row=3)
    pdf.ln(6)

    # ---- Detailed plot breakdown -------------------------------------- #
    pdf.body_heading("Detailed Plot Breakdown")

    headers = ["Plot", "Plot Size (m²)", "Road Ded. (m²)",
               "Green Ded. (m²)", "Net Land (m²)"]
    col_widths = [34, 37, 37, 37, 35]

    _table_header(pdf, headers, col_widths)

    total_plot = total_road = total_green = total_net = 0
    pdf.set_font(GIGA, "", 9.5)
    for i, plot in enumerate(results["plots"]):
        plot_size = round(plot["plot_size"])
        road = round(plot["road_deduction"])
        green = round(plot["green_deduction"])
        net = round(plot["net_plot_size"])
        total_plot += plot_size
        total_road += road
        total_green += green
        total_net += net

        row = [f"Plot {i + 1}", f"{plot_size:,}", f"{road:,}",
               f"{green:,}", f"{net:,}"]
        _table_row(pdf, row, col_widths, striped=(i % 2 == 1))

    # Single total row, AFTER the loop (was previously emitted per-plot)
    total_row = ["Total", f"{total_plot:,}", f"{total_road:,}",
                 f"{total_green:,}", f"{total_net:,}"]
    _table_total_row(pdf, total_row, col_widths)

    # output() returns the PDF bytes directly — no temp file needed
    return BytesIO(bytes(pdf.output()))


# ----------------------- PDF drawing helpers -----------------------#
def _kpi_banner(pdf, label, value):
    """Full-width Cymaris band with a label and a large value."""
    x, y, w = pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin
    h = 18
    pdf.set_fill_color(*hex_to_rgb(CYMARIS))
    pdf.rect(x, y, w, h, style="F", round_corners=True, corner_radius=2)
    pdf.set_xy(x + 5, y + 3)
    pdf.set_font(GIGA_MEDIUM, "", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 5, label.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x + 5)
    pdf.set_font(GIGA, "B", 16)
    pdf.cell(0, 8, value)
    pdf.set_xy(x, y + h)
    pdf.set_text_color(*hex_to_rgb(NOXEN))


def _stat_cards(pdf, cards, per_row=3):
    x0 = pdf.l_margin
    gap = 4
    avail = pdf.w - pdf.l_margin - pdf.r_margin
    cw = (avail - gap * (per_row - 1)) / per_row
    ch = 18
    row_y = pdf.get_y()
    for idx, (label, value) in enumerate(cards):
        col = idx % per_row
        if col == 0 and idx > 0:
            row_y += ch + gap
        x = x0 + col * (cw + gap)
        y = row_y
        pdf.set_fill_color(*hex_to_rgb(NIVELLE))
        pdf.set_draw_color(*hex_to_rgb(CLARIA))
        pdf.set_line_width(0.3)
        pdf.rect(x, y, cw, ch, style="DF", round_corners=True, corner_radius=2)
        pdf.set_xy(x + 4, y + 3.5)
        pdf.set_font(GIGA_MEDIUM, "", 7.5)
        pdf.set_text_color(*hex_to_rgb(MUTED))
        pdf.cell(cw - 8, 4, label.upper())
        pdf.set_xy(x + 4, y + 9)
        pdf.set_font(GIGA, "B", 13)
        pdf.set_text_color(*hex_to_rgb(NOXEN))
        pdf.cell(cw - 8, 6, value)
    pdf.set_xy(x0, row_y + ch)


def _table_header(pdf, headers, widths):
    pdf.set_fill_color(*hex_to_rgb(NOXEN))
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(GIGA_SEMIBOLD, "", 9)
    for h, w in zip(headers, widths):
        pdf.cell(w, 9, h, border=0, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(*hex_to_rgb(NOXEN))


def _table_row(pdf, row, widths, striped=False):
    if striped:
        pdf.set_fill_color(*hex_to_rgb(CLARIA))
    else:
        pdf.set_fill_color(255, 255, 255)
    for data, w in zip(row, widths):
        pdf.cell(w, 8, data, border=0, align="C", fill=True)
    pdf.ln()


def _table_total_row(pdf, row, widths):
    pdf.set_fill_color(*hex_to_rgb(CYMARIS))
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(GIGA, "B", 9.5)
    for data, w in zip(row, widths):
        pdf.cell(w, 9, data, border=0, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(*hex_to_rgb(NOXEN))


# ----------------------- Excel Report Generator -----------------------#
def generate_excel_report(results, total_price, price_per_m2):
    output = BytesIO()

    summary_df = pd.DataFrame({
        "Metric": [
            "Total Project Price (EUR)",
            "Total Buildable Area (m²)",
            "Residential Buildable Area (m²)",
            "Commercial Buildable Area (m²)",
            "Total Deductions (m²)",
            "Road Deduction (m²)",
            "Public Green Deduction (m²)",
            "Coverage Area (m²)",
            "Price per Buildable m² (EUR)",
        ],
        "Value": [
            total_price,
            results["total_buildable_area"],
            results["residential_buildable_area"],
            results["commercial_buildable_area"],
            results["total_road_deduction"] + results["total_green_deduction"],
            results["total_road_deduction"],
            results["total_green_deduction"],
            results.get("total_coverage_area", 0),
            round(price_per_m2, 2),
        ],
    })

    plot_details = []
    for plot in results["plots"]:
        for j, zone_buildable_area in enumerate(plot["zone_buildable_areas"]):
            zone = plot["zones"][j]
            plot_details.append({
                "Plot Serial Number": plot["serial_number"],
                "Plot Area (m²)": plot["plot_size"],
                "Road Deduction (m²)": plot["road_deduction"],
                "Public Green Deduction (m²)": plot["green_deduction"],
                "Net Land Area (m²)": plot["net_plot_size"],
                "Zone": f"Zone {j + 1}",
                "Zone Percentage (%)": zone["percentage"],
                "Density Factor (%)": zone["density_factor"],
                "Zone Type": zone["density_type"],
                "Buildable Area (m²)": zone_buildable_area,
            })
    plot_df = pd.DataFrame(plot_details)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Summary", startrow=1)
        plot_df.to_excel(writer, index=False, sheet_name="Plot Details", startrow=1)
        _style_workbook(writer, {"Summary": summary_df, "Plot Details": plot_df})

    output.seek(0)
    return output


def _style_workbook(writer, frames):
    """Apply the Allora palette to the xlsx header rows and a title band."""
    book = writer.book
    title_fmt = book.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": NOXEN,
        "font_size": 13, "valign": "vcenter", "font_name": "Calibri",
    })
    header_fmt = book.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": NAVARIS,
        "border": 1, "border_color": "#FFFFFF", "valign": "vcenter",
    })
    for sheet_name, df in frames.items():
        ws = writer.sheets[sheet_name]
        ncols = max(len(df.columns), 1)
        ws.merge_range(0, 0, 0, ncols - 1, f"Allora  ·  {sheet_name}", title_fmt)
        ws.set_row(0, 22)
        for col, name in enumerate(df.columns):
            ws.write(1, col, name, header_fmt)
            width = max(len(str(name)), *(df[name].astype(str).map(len).tolist() or [0]))
            ws.set_column(col, col, min(max(width + 3, 12), 40))
        ws.freeze_panes(2, 0)
