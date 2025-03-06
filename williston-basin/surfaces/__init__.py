from os import environ

environ["MPLBACKEND"] = "module://itermplot"
environ["ITERMPLOT"] = "rv"

from shapely.ops import transform
from typer import Typer, Argument
from pandas import read_csv
from IPython import embed
import geopandas as G
from numpy import meshgrid, linspace, nan
from scipy.interpolate import CloughTocher2DInterpolator
import rasterio
from rasterio.features import geometry_mask
from pathlib import Path
from shapely.geometry import LineString
from pyproj import Transformer
from .model import (
    create_geological_model,
    create_bounds,
    create_model_constraints,
    run_loop_demo,
)
from LoopStructural.visualisation import Loop3DView

app = Typer()

# Albus equal area projection of the lower 48 states
# Good CRS for the Williston Basin
crs = "EPSG:5069"
# U.S. Survey foot to meter conversion
ft_to_m = 0.3048006096012192

here = Path(__file__).parent.parent


@app.command("summarize-data")
def summarize_data():
    """Summarize the well data"""
    well_info = read_well_data()
    max_depth = well_info.iloc[:, 1:].min(axis=1)
    n_surfaces = well_info.iloc[:, 1:].count(axis=1)
    well_info = well_info[["geometry"]].assign(
        max_depth=max_depth, n_surfaces=n_surfaces
    )

    outdir = here / "output"
    outdir.mkdir(exist_ok=True)

    well_info.to_file("output/well-info.gpkg", layer="metadata", driver="GPKG")

    # Create a buffer around the wells to form a rough basin outline
    bounds = create_bounds(well_info)
    # Save the buffer as bounds
    bounds.to_file("output/well-info.gpkg", layer="bounds", driver="GPKG")


@app.command("create-surfaces")
def process_well_data():
    """Ingest well data and create surfaces using a Scipy interpolator"""
    gdf = read_well_data()
    model_type = "scipy"

    # Create a buffer around the wells to form a rough basin outline
    bounds = create_bounds(gdf)

    grid = meshgrid_2d(bounds, 1000)
    xmin, ymin, xmax, ymax = bounds.total_bounds

    size_args = dict(width=grid[0].shape[1], height=grid[0].shape[0])

    _transform = rasterio.transform.from_bounds(xmin, ymax, xmax, ymin, **size_args)

    # Each row of the spreadsheet is a well

    mask = geometry_mask(bounds.geometry, out_shape=grid[0].shape, transform=_transform)

    dirname = here / "output" / model_type
    dirname.mkdir(parents=True, exist_ok=True)

    for name in gdf.iloc[:, 1:]:
        df1 = gdf[["geometry", name]].dropna(subset=[name])

        # Get the formation name
        formation = name
        # Get the xy coordinates of the wells
        xy = list(zip(df1.geometry.x, df1.geometry.y))
        # Get the formation top depths
        tops = df1[name].values
        create_interpolated_raster(
            xy, tops, model_type, formation, grid, mask, _transform
        )


def create_interpolated_raster(xy, z, model_type, formation, grid, mask, _transform):
    dirname = here / "output" / model_type
    dirname.mkdir(parents=True, exist_ok=True)

    size_args = dict(width=grid[0].shape[1], height=grid[0].shape[0])

    print(f"Processing {formation} formation")

    interpolator = CloughTocher2DInterpolator(xy, z, rescale=True)
    Z = interpolator(*grid)

    with rasterio.open(
        str(dirname / f"{formation}.tif"),
        "w",
        driver="GTiff",
        **size_args,
        count=1,
        crs=crs,
        transform=_transform,
        dtype=Z.dtype,
    ) as dst:
        Z[mask] = nan
        dst.write(Z, 1)


@app.command("model")
def create_model(show: bool = False):
    """Create a geological model from the well data using Loop3D"""
    gdf = read_well_data()
    model = create_geological_model(gdf)
    model_type = "loop"

    df, column = create_model_constraints(gdf)

    # Randomly sample data by factor of 100 for testing
    df = df.sample(frac=0.01)

    model.set_model_data(df)
    strata = []
    for strat in column.keys():
        s0 = model.create_and_add_foliation(
            strat, interpolatortype="FDI", nelements=1e4
        )
        strata.append(s0)
    model.set_stratigraphic_column(column)

    if show:
        viewer = Loop3DView(model)
        for s0 in strata:
            # viewer.plot_data(s0, scale=200)
            viewer.plot_surface(s0, value=1)
        # viewer.plot_block_model(scalar_bar=True, slicer=True)
        viewer.show(interactive=True)
        return

    model.update()

    surfaces = model.get_stratigraphic_surfaces()

    bounds = create_bounds(gdf)

    grid = meshgrid_2d(bounds, 1000)
    xmin, ymin, xmax, ymax = bounds.total_bounds

    size_args = dict(width=grid[0].shape[1], height=grid[0].shape[0])

    _transform = rasterio.transform.from_bounds(xmin, ymax, xmax, ymin, **size_args)
    mask = geometry_mask(bounds.geometry, out_shape=grid[0].shape, transform=_transform)

    unit_names = column["main"].keys()
    for name, surface in zip(unit_names, surfaces):
        vertices = surface.vertices
        xy = vertices[:, :2]
        Z = vertices[:, 2]
        create_interpolated_raster(xy, Z, model_type, name, grid, mask, _transform)

    # grid = meshgrid_2d(create_bounds(gdf), 1000)
    # Get surfaces for each stratigraphic unit
    # embed()


app.command("loop-demo")(run_loop_demo)


sections = [
    [
        (-106.6000, 48.9654),
        (-100.8362, 45.7890),
    ],
    [
        (-107.0315, 48.1072),
        (-99.8404, 47.4613),
    ],
]


@app.command("cross-sections")
def build_cross_sections(model_type: str = Argument("loop")):
    print(f"Building cross sections for {model_type} model")
    """Create a cross section of the basin between two points, and plot with matplotlib"""
    # Create geometry for the cross section
    for section in sections:
        start, end = section
        line = LineString([start, end])
        transformer = Transformer.from_crs(4326, crs, always_xy=True)
        line_prj = transform(transformer.transform, line)

        # Load the raster data surface-by-surface and interpolate along the cross section
        series = {}

        for file in (here / "output" / model_type).glob("*.tif"):
            key = file.stem
            with rasterio.open(file) as src:
                # # Extract the raster data along the cross section
                xy = [
                    line_prj.interpolate(d).coords[0]
                    for d in range(0, int(line_prj.length), 100)
                ]
                # # Extract the raster values at the cross section points
                values = list(src.sample(xy))
                series[key] = values

        # Plot the cross section

        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 3))
        ax = plt.subplot(111)

        for key, values in series.items():
            ax.plot(values, label=key)
        # ax.legend()
        plt.show()


def meshgrid_2d(bounds, n_samples):
    # Create a regular grid of points within the bounds
    xmin, ymin, xmax, ymax = bounds.total_bounds
    aspect_ratio = (xmax - xmin) / (ymax - ymin)
    nsx, nsy = n_samples, int(n_samples / aspect_ratio)
    if aspect_ratio > 1:
        nsx, nsy = nsy, nsx

    return meshgrid(linspace(xmin, xmax, nsx), linspace(ymin, ymax, nsy))


def read_well_data():
    df = read_csv("data/Williston_Basin_well_data.csv")
    # Set index to WELL_ID
    df.set_index("WELL_ID", inplace=True)
    # Well data starts at column 7, convert to meters
    df.iloc[:, 6:] *= ft_to_m

    # Convert to GeoDataFrame using LAT and LON columns
    gdf = G.GeoDataFrame(
        df, geometry=G.points_from_xy(df.LONG, df.LAT, crs="EPSG:4326")
    )
    gdf = gdf.iloc[:, 6:]
    # Move geometry to the beginning, and keep only formation top depths
    gdf = gdf[
        ["geometry"]
        + [col for col in gdf.columns if (col != "geometry" and "TOP" in col)]
    ]

    return gdf.to_crs(crs)


if __name__ == "__main__":
    app()
