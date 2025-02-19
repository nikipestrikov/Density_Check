import streamlit as st

from Calculations import green_area_formula, calculate_totals
from reports import generate_excel_report, generate_pdf_report

# Streamlit UI
st.sidebar.image("logo.png", width=75)
st.markdown("<h1 style='text-align: center;'>Project Density Analysis</h1>", unsafe_allow_html=True)

st.sidebar.header("Plot Configuration")
num_plots = st.sidebar.number_input("Number of Plots", min_value=1, max_value=10, value=1, step=1)

project_name = st.sidebar.text_input("Project Name", value="Area and Plot #")

apply_efficiency_incentive = st.sidebar.checkbox("Apply 5% Efficiency Incentive")
price_toggle = st.sidebar.radio("Specify Price For", ["Each Plot", "Total Project"])

green_allocation_method = st.sidebar.radio("Public Green Allocation Method", ["Proportional", "Custom"])
custom_green_allocations = []

total_price = 0
plots = []

if price_toggle == "Total Project":
    total_price_input = st.text_input("Total Project Price (€)", value="100,000")
    try:
        total_price = int(total_price_input.replace(",", ""))  # Remove commas and convert to integer
        if total_price < 0:
            st.error("Total project price must be a positive number.")
            total_price = 0
        else:
            # Re-display the value with commas
            total_price_input = f"{total_price:,}"
    except ValueError:
        st.error("Please enter a valid number for total project price.")
        total_price = 0

for i in range(num_plots):
    with st.sidebar.expander(f"Plot {i + 1} Configuration", expanded=False):
        serial_number = st.text_input(f"Plot {i + 1} Serial Number", value=f"Plot-{i + 1}", key=f"serial_{i}")
        plot_size_input = st.text_input(f"Plot {i + 1} Size (m²)", value="1,000", key=f"plot_size_{i}")
        try:
            plot_size = int(plot_size_input.replace(",", ""))  # Remove commas and convert to integer
            if plot_size < 0:
                st.error("Plot size must be a positive number.")
                plot_size = 0
            else:
                # Re-display the value with commas
                plot_size_input = f"{plot_size:,}"
        except ValueError:
            st.error("Please enter a valid number for plot size.")
            plot_size = 0
        is_parceled = st.checkbox(f"Is Plot {i + 1} Parceled?", value=True, key=f"parceled_{i}")
        road_deduction_percent = 0

        if not is_parceled:
            road_deduction_percent = st.slider(f"Plot {i + 1} Road Deduction (%)", min_value=0, max_value=50, value=10, step=1, key=f"road_{i}")

        coverage_percent = st.slider(
            f"Plot {i + 1} Coverage (%)",
            min_value=0,
            max_value=100,
            value=50,  # default or adjust as needed
            step=1,
            key=f"coverage_{i}"
        )

        num_zones = st.number_input(f"Number of Zones", min_value=1, max_value=3, value=1, step=1, key=f"zones_{i}")
        zones = []
        remaining_percentage = 100

        for j in range(int(num_zones)):
            percentage = st.slider(f"Zone {j + 1} %", min_value=0, max_value=remaining_percentage, value=remaining_percentage, step=1, key=f"zone_{i}_{j}")
            remaining_percentage -= percentage
            density_factor = st.number_input(f"Zone {j + 1} Density Factor (%)", min_value=0, value=50, step=1, key=f"density_{i}_{j}")
            density_type = st.selectbox(f"Zone {j + 1} Type", ["Residential", "Commercial"], key=f"type_{i}_{j}")
            zones.append({"percentage": percentage, "density_factor": density_factor, "density_type": density_type})

        plot_price = st.number_input(f"Price for Plot {i + 1}", min_value=0, step=1, format="%d", key=f"price_{i}") if price_toggle == "Each Plot" else 0
        total_price += plot_price

        plots.append({"serial_number": serial_number, "plot_size": plot_size, "is_parceled": is_parceled, "road_deduction_percent": road_deduction_percent, "zones": zones, "coverage_percent": coverage_percent
})

if green_allocation_method == "Custom":
    st.sidebar.header("Custom Green Area Allocation")
    allocated_sum = 0

    for i in range(num_plots):
        max_allocation = 100 - allocated_sum
        max_allocation = min(max_allocation, int(plots[i]["plot_size"] / green_area_formula(sum(p["plot_size"] for p in plots)) * 100))
        allocation = st.sidebar.slider(
            f"Green Allocation for Plot {i + 1} (%)",
            min_value=0,
            max_value=max_allocation,
            value=min(100 // num_plots, max_allocation),
            step=1,
            key=f"custom_green_{i}"
        )
        allocated_sum += allocation
        custom_green_allocations.append(allocation)

# Calculate button with session state handling
if st.button("Calculate"):
    # Perform calculations
    results = calculate_totals(plots, apply_efficiency_incentive, green_allocation_method, custom_green_allocations)
    price_per_m2 = total_price / results['total_buildable_area'] if results['total_buildable_area'] else 0

    # Store results in session state
    st.session_state["results"] = results
    st.session_state["price_per_m2"] = price_per_m2
    st.session_state["total_price"] = total_price
    st.session_state["calculated"] = True  # Set a flag to indicate that calculations have been performed

# Check if calculations exist in session state
if "calculated" in st.session_state and st.session_state["calculated"]:
    results = st.session_state["results"]
    price_per_m2 = st.session_state["price_per_m2"]
    total_price = st.session_state["total_price"]

    # Highlighted Statistics
    st.markdown(
        f"<div style='background-color:#d4edda;padding:10px;border-radius:5px;margin-bottom:10px;'>" +
        f"<b>Price per Buildable Area:</b> €{price_per_m2:,.0f}/m²</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='background-color:#fff3cd;padding:10px;border-radius:5px;margin-bottom:10px;'>" +
        f"<b>Total Buildable Area:</b> {results['total_buildable_area']:,} m² " +
        f"<details><summary>Click to expand</summary>" +
        f"Residential: {results['residential_buildable_area']:,} m²<br>" +
        f"Commercial: {results['commercial_buildable_area']:,} m²" +
        f"</details></div>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='background-color:#f8d7da;padding:10px;border-radius:5px;margin-bottom:10px;'>" +
        f"<b>Total Deductions:</b> {results['total_road_deduction'] + results['total_green_deduction']:,} m² " +
        f"<details><summary>Click to expand</summary>" +
        f"Road: {results['total_road_deduction']:,} m²<br>" +
        f"Public Green: {results['total_green_deduction']:,} m²" +
        f"</details></div>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='background-color:#7688f1;padding:10px;border-radius:5px;margin-bottom:10px;'>" +
        f"<b>Coverage Area:</b> {results['total_coverage_area']:,} m² " +
        f"<details><summary>Click to expand</summary>" +
        f"</details></div>",
        unsafe_allow_html=True
    )
    # Excel Export
    excel_data = generate_excel_report(results, total_price, price_per_m2)
    st.download_button(
        label="Download Excel Report",
        data=excel_data,
        file_name="density_calculation_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # PDF Export
    try:
        pdf_data = generate_pdf_report(results, total_price, price_per_m2, project_name)
        st.download_button(
            label="Download PDF Report",
            data=pdf_data,
            file_name="density_calculation_results.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Failed to generate PDF: {e}")

    # Detailed Breakdown for Each Plot
    st.subheader("Detailed Calculation Breakdown")
    for i, plot in enumerate(results['plots']):
        with st.expander(f"Plot {i + 1} ({plot['serial_number']})"):
            st.markdown(f"**Plot Area:** {plot['plot_size']:,} m²")
            st.markdown(f"**Road Deduction:** {plot['road_deduction']:,} m²")
            st.markdown(f"**Public Green Allocated:** {plot['green_deduction']:,} m²")
            st.markdown(f"**Net Land Area:** {plot['net_plot_size']:,} m²")

            for j, zone_buildable_area in enumerate(plot["zone_buildable_areas"]):
                zone = plot["zones"][j]
                st.markdown(
                    f"**Zone {j + 1}:** {zone['percentage']}% | Density Factor: {zone['density_factor']}% | " +
                    f"Type: {zone['density_type']} | Buildable Area: {zone_buildable_area:,} m²"
                )

        for j, zone_buildable_area in enumerate(plot["zone_buildable_areas"]):
            zone = plot["zones"][j]
            st.markdown(
                f"**Zone {j + 1}:** {zone['percentage']}% | "
                f"Density Factor: {zone['density_factor']}% | "
                f"Type: {zone['density_type']} | "
                f"Buildable Area: {zone_buildable_area:,} m²"
            )
