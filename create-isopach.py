#!/usr/bin/env python
"""Script to create an isopach map from Macrostrat units"""

from pathlib import Path

# URL encoding
from urllib.parse import urlencode

import geopandas as G
import pandas as P
import requests
from rich import print
from typer import Option, Typer

app = Typer()

# These could become environment variables
cache_dir = Path("cache")
macrostrat_api = "https://dev2.macrostrat.org/api/v2"


def _AgeDependency(value: float | str | None, type: str):
    if value is None:
        return None
    if isinstance(value, float):
        return value
    try:
        return float(value)
    except ValueError:
        interval = get_interval(value)
        return float(interval[type])


def MinAgeDependency(value: float | str | None):
    return _AgeDependency(value, "t_age")


def MaxAgeDependency(value: float | str | None):
    return _AgeDependency(value, "b_age")


@app.command(no_args_is_help=True)
def isopach_map(
    output_file: Path,
    strat_name: str = None,
    crs="EPSG:5070",
    min_age=Option(None, help="Minimum (upper) age", callback=MinAgeDependency),
    max_age=Option(None, help="Maximum (lower) age", callback=MaxAgeDependency),
    lith=Option(None, help="Lithology to filter by"),
    bounds: Path = Option(None, help="Bounds to filter by"),
    n_samples: int = Option(1000, help="Number of samples for rasterization"),
):
    """Create a map of isopach data for a given stratigraphic unit"""
    print(f"Creating isopach map for {strat_name}")

    all_columns = get_all_columns()

    # column_centers = all_columns["geometry"].centroid

    if min_age is not None and max_age is not None and min_age > max_age:
        raise ValueError("Minimum age must be less than maximum age")

    params = {"strat_name": strat_name, "age_top": min_age, "age_bottom": max_age}
    if lith is not None:
        # Get level of the hierarchy to query at
        lith_level = get_lith_level(lith)
        params[lith_level] = lith

    units = P.json_normalize(get_macrostrat("units", params))

    def commasep(x):
        return ",".join([str(i) for i in x if i != N.nan])

    commasep = lambda x: ",".join([str(i) for i in x])

    # Group by column
    units = units.groupby("col_id").agg(
        {
            "unit_id": commasep,
            "unit_name": commasep,
            "t_age": "min",
            "b_age": "max",
            "min_thick": "sum",
            "max_thick": "sum",
        }
    )

    units = all_columns.merge(units, left_on="col_id", right_on="col_id", how="left")

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
    if crs is not None:
        units = units.to_crs(crs)

    # Clip to bounds
    if bounds is not None:
        _bounds = G.read_file(bounds)
        _bounds = _bounds.to_crs(units.crs)
        units = G.clip(units, _bounds)

    # Copy the geodataframe
    units1 = units.copy()
    units1.dropna(subset=["unit_id"], inplace=True)
    units1.to_file(output_file.with_suffix(".gpkg"), driver="GPKG")

    if output_file.suffix == ".tif":
        rasterize = True

    if not rasterize:
        return

    # Set NaN values to 0
    units.fillna(0, inplace=True)

    # Get centroids
    ctr = units["geometry"].centroid
    max_thick = units["max_thick"]

    # Interpolate the thickness to the centroids
    import numpy as N
    import rasterio as R
    import scipy.interpolate as I
    from rasterio.features import geometry_mask

    _bounds = units.total_bounds
    xmin, ymin, xmax, ymax = _bounds

    # Get a regular grid of points
    # Note: equal spacing is not guaranteed
    X, Y = N.meshgrid(
        N.linspace(xmin, xmax, n_samples), N.linspace(ymin, ymax, n_samples)
    )

    interpolator = I.CloughTocher2DInterpolator(
        list(zip(ctr.x, ctr.y)), max_thick, rescale=True
    )
    Z = interpolator(X, Y)

    # Create a raster from the interpolated data
    dset = R.open(
        output_file.with_suffix(".tif"),
        "w",
        driver="GTiff",
        height=Z.shape[1],
        width=Z.shape[0],
        count=1,
        dtype=Z.dtype,
        crs=units.crs,
        transform=R.transform.from_bounds(
            xmin, ymax, xmax, ymin, width=Z.shape[0], height=Z.shape[1]
        ),
    )

    msk = geometry_mask(
        units["geometry"],
        out_shape=(n_samples, n_samples),
        transform=dset.transform,
    )
    Z[msk] = N.nan
    Z[Z < 0] = N.nan
    dset.write(Z, 1)


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


def get_macrostrat(uri, params=None):
    if params is not None:
        _params = {k: v for k, v in params.items() if v is not None}
        uri += "?" + urlencode(_params)
    uri = macrostrat_api + "/" + uri
    print(f"Fetching {uri}")
    data = requests.get(uri).json()
    return data["success"]["data"]


def get_lith_level(lith_name):
    lith = get_macrostrat("defs/lithologies", {"lith": lith_name})
    if len(lith) == 0:
        raise ValueError(f"Could not find lithology {lith}")
    if len(lith) > 1:
        raise ValueError(
            f"Found multiple lithologies for {lith}, this is not supported"
        )
    lith = lith[0]
    # Walk the hierarchy in reverse order to find the highest level
    levels = ["class", "type", "group", "name"]
    for level in levels:
        if lith[level] == lith_name:
            if level == "name":
                return "lith"
            else:
                return "lith_" + level


def get_interval(interval_name):
    intervals = get_macrostrat("defs/intervals", {"name": interval_name})
    if len(intervals) == 0:
        raise ValueError(f"Could not find interval {interval_name}")
    if len(intervals) > 1:
        raise ValueError(
            f"Found multiple intervals for {interval_name}, this is not supported"
        )
    return intervals[0]


if __name__ == "__main__":
    app()
