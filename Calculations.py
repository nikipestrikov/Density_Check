# ----------------------- Utility Functions -----------------------#

# Function to calculate net land area based on plot type
def calculate_net_land_area(plot_size, is_parceled, road_deduction_percent, green_percentage):
    if is_parceled:
        # If parceled, no road or green deductions apply
        return plot_size, 0, 0

     # Calculate road deduction
    road_deduction = plot_size * (road_deduction_percent / 100)
    area_after_road = plot_size - road_deduction

    # Calculate green deduction on the area remaining after road deduction
    green_deduction = area_after_road * (green_percentage / 100)

    # Calculate net area
    net_area = area_after_road - green_deduction

    return round(net_area), round(road_deduction), round(green_deduction)

# Green area deduction based on total combined plot size
def green_area_formula(total_area):
    match total_area:
        case _ if total_area < 800:
            return 0
        case _ if 800 <= total_area < 1500:
            return 5
        case _ if 1500 <= total_area < 2500:
            return 10
        case _ if 2500 <= total_area < 10000:
            return 15
        case _ if 10000 <= total_area < 50000:
            return 17
        case _:
            return 18

# ----------------------- Calculation Functions -----------------------#

# Function to calculate totals and handle green area allocation
def calculate_totals(plots, apply_efficiency_incentive, green_allocation_method, custom_green_allocations):
    total_net_area = 0
    total_road_deduction = 0
    total_green_deduction = 0
    commercial_area = 0
    residential_area = 0
    commercial_density_sum = 0
    residential_density_sum = 0

    # ─────────────────────────────────────────────────────────
    # Optional: Track coverage & floors across all plots
    # ─────────────────────────────────────────────────────────
    total_coverage_area = 0
    total_max_floors = 0
    total_extra_floors_cost = 0

    for plot in plots:
        # ─────────────────────────────────────────────────────
        # Existing logic: handle road/green deductions or parcels
        # ─────────────────────────────────────────────────────
        if plot["is_parceled"]:
            plot["net_plot_size"] = plot["plot_size"]
            plot["road_deduction"] = 0
            plot["green_deduction"] = 0
        else:
            road_deduction = plot["plot_size"] * (plot["road_deduction_percent"] / 100)
            area_after_road = plot["plot_size"] - road_deduction

            green_percentage = green_area_formula(area_after_road)
            green_deduction = area_after_road * (green_percentage / 100)

            net_plot_size = area_after_road - green_deduction

            plot["net_plot_size"] = net_plot_size
            plot["road_deduction"] = road_deduction
            plot["green_deduction"] = green_deduction

            total_net_area += net_plot_size
            total_road_deduction += road_deduction
            total_green_deduction += green_deduction

        # ─────────────────────────────────────────────────────
        # 1) Calculate coverage area (if coverage_percent exists)
        # ─────────────────────────────────────────────────────
        coverage_percent = plot.get("coverage_percent", 0)
        coverage_area = plot["net_plot_size"] * (coverage_percent / 100)
        plot["coverage_area"] = coverage_area
        total_coverage_area += coverage_area  # Summation if needed

        # ─────────────────────────────────────────────────────
        # 2) Determine how many floors are possible
        # ─────────────────────────────────────────────────────
        max_height = plot.get("max_height", 0)
        floor_height = plot.get("floor_height", 0)
        if floor_height > 0:
            base_floors = int(max_height // floor_height)
        else:
            base_floors = 0  # If no valid floor height, no floors

        # ─────────────────────────────────────────────────────
        # 3) Handle extra floors logic (if toggled on this plot)
        # ─────────────────────────────────────────────────────
        allow_extra_floors = plot.get("allow_extra_floors", False)
        extra_floors = plot.get("extra_floors", 0)
        cost_per_extra_floor = plot.get("cost_per_extra_floor", 0.0)

        if allow_extra_floors and extra_floors > 0:
            total_floors = base_floors + extra_floors
            extra_floors_cost = extra_floors * cost_per_extra_floor
        else:
            total_floors = base_floors
            extra_floors_cost = 0.0

        plot["max_floors"] = total_floors
        plot["extra_floors_cost"] = extra_floors_cost

        total_max_floors += total_floors
        total_extra_floors_cost += extra_floors_cost

        # ─────────────────────────────────────────────────────
        # 4) Incorporate coverage area with floors if needed
        # ─────────────────────────────────────────────────────
        # "max_buildable_area" depends on coverage and total floors
        max_buildable_area = coverage_area * total_floors
        plot["max_buildable_area"] = max_buildable_area

        # ─────────────────────────────────────────────────────
        # Continue your existing zone-based buildable area logic
        # ─────────────────────────────────────────────────────
        plot["zone_buildable_areas"] = []
        for zone in plot["zones"]:
            zone_area = plot["net_plot_size"] * (zone["percentage"] / 100)
            density_factor = zone["density_factor"]
            density_type = zone["density_type"].lower()

            match density_type:
                case "commercial":
                    commercial_area += zone_area
                    commercial_density_sum += zone_area * density_factor
                case "residential":
                    residential_area += zone_area
                    residential_density_sum += zone_area * density_factor
                case _:
                    pass  # Handle unrecognized density types

            buildable_area = (zone_area * density_factor) / 100
            plot["zone_buildable_areas"].append(round(buildable_area))

    # ─────────────────────────────────────────────────────────
    # Calculate averages & buildable areas for commercials/residential
    # ─────────────────────────────────────────────────────────
    commercial_density_avg = (commercial_density_sum / commercial_area) if commercial_area else 0
    residential_density_avg = (residential_density_sum / residential_area) if residential_area else 0

    commercial_buildable_area = (commercial_area * commercial_density_avg) / 100
    residential_buildable_area = (residential_area * residential_density_avg) / 100

    incentive_area = 0
    if apply_efficiency_incentive:
        incentive_area = 0.05 * (commercial_buildable_area + residential_buildable_area)

    total_buildable_area = commercial_buildable_area + residential_buildable_area + incentive_area

    # ─────────────────────────────────────────────────────────
    # Return dictionary including coverage & floors if needed
    # ─────────────────────────────────────────────────────────
    return {
        "total_net_area": round(total_net_area),
        "total_road_deduction": round(total_road_deduction),
        "total_green_deduction": round(total_green_deduction),
        "commercial_avg_density": round(commercial_density_avg),
        "residential_avg_density": round(residential_density_avg),
        "commercial_buildable_area": round(commercial_buildable_area),
        "residential_buildable_area": round(residential_buildable_area),
        "incentive_area": round(incentive_area),
        "total_buildable_area": round(total_buildable_area),
        # Coverage & floor-related totals
        "total_coverage_area": round(total_coverage_area),
        "total_max_floors": total_max_floors,
        "total_extra_floors_cost": round(total_extra_floors_cost),
        "plots": plots
    }

#Function to calculate coverage area#
def calculate_coverage_area(net_plot_size: float, coverage_percent: float) -> float:
    if coverage_percent < 0 or coverage_percent > 100:
        raise ValueError("Coverage percent must be between 0 and 100.")
    return net_plot_size * (coverage_percent / 100)