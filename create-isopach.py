#!/usr/bin/env python
"""Script to create an isopach map from Macrostrat units"""

from pathlib import Path

from IPython import embed
from typer import Typer

app = Typer()


@app.command()
def isopach_map(strat_name: str, crs="EPSG:5070"):
    """Create a map of isopach data for a given stratigraphic unit"""
    print(f"Creating isopach map for {strat_name}")

    import geopandas as G

    # Albers lower 48
    crs = "EPSG:5070"

    all_columns = G.read_file(
        "https://dev2.macrostrat.org/api/v2/columns?project_id=1&format=geojson_bare"
    ).to_crs(crs)

    # column_centers = all_columns["geometry"].centroid

    matched_units = G.read_file(
        f"https://dev2.macrostrat.org/api/v2/units?strat_name={strat_name}&format=geojson_bare"
    ).to_crs(crs)

    # Expand the matched units to the column footprints

    units = all_columns.sjoin(matched_units, how="left")

    # Rename columns
    units = units.rename(columns={"col_id_left": "col_id"})

    # Drop all columns except the column id and the geometry
    units = units[
        [
            "col_id",
            "unit_id",
            "col_name",
            "col_group",
            "geometry",
            "t_age",
            "b_age",
            "min_thick",
            "max_thick",
        ]
    ]

    units.dropna(subset=["unit_id"], inplace=True)

    # Dump the units to a file
    output_path = Path("output")
    output_path.mkdir(exist_ok=True)

    units.to_file(output_path / f"{strat_name}-isopach.gpkg", driver="GPKG")


if __name__ == "__main__":
    app()
