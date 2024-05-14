#!/usr/bin/env python
"""Script to create an isopach map from Macrostrat units"""

from pathlib import Path

# URL encoding
from urllib.parse import urlencode

import geopandas as G
import pandas as P
import requests
from typer import Typer

app = Typer()

# These could become environment variables
cache_dir = Path("cache")
macrostrat_api = "https://dev2.macrostrat.org/api/v2"


def get_all_columns(project_id=1):
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"columns-project-{project_id}.gpkg"

    if cache_file.exists():
        return G.read_file(cache_file)

    params = {"project_id": project_id, "format": "geojson_bare"}
    uri = macrostrat_api + "/columns?" + urlencode(params)
    columns = G.read_file(uri)
    columns.to_file(cache_file, driver="GPKG")
    return columns


@app.command()
def isopach_map(
    strat_name: str = None,
    crs="EPSG:5070",
    rasterize=False,
    macrostrat_api="https://dev2.macrostrat.org/api/v2",
):
    """Create a map of isopach data for a given stratigraphic unit"""
    print(f"Creating isopach map for {strat_name}")

    all_columns = get_all_columns()

    # column_centers = all_columns["geometry"].centroid

    params = {"strat_name": strat_name}
    uri = macrostrat_api + "/units?" + urlencode(params)

    data = requests.get(uri).json()
    units = P.json_normalize(data["success"]["data"])

    units = all_columns.merge(units, left_on="col_id", right_on="col_id")

    # Rename columns
    units = units.rename(columns={"col_id_left": "col_id"})

    # Drop all columns except the column id and the geometry
    units = units[
        [
            "col_id",
            "unit_id",
            "unit_name",
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
