from shapely.ops import transform
from typer import Typer
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
from .model import create_geological_model, create_bounds

app = Typer()

# Albus equal area projection of the lower 48 states
# Good CRS for the Williston Basin
crs = "EPSG:5069"
# U.S. Survey foot to meter conversion
ft_to_m = 0.3048006096012192

here = Path(__file__).parent.parent


@app.command("create-surfaces")
def process_well_data():
    """Ingest well data and create surfaces using a Scipy interpolator"""
    gdf = read_well_data()

    well_info = gdf.copy()
    max_depth = well_info.iloc[:, 1:].min(axis=1)
    n_surfaces = well_info.iloc[:, 1:].count(axis=1)
    well_info = well_info[["geometry"]].assign(
        max_depth=max_depth, n_surfaces=n_surfaces
    )

    well_info.to_file("output/well-info.gpkg", layer="metadata", driver="GPKG")

    # Create a buffer around the wells to form a rough basin outline
    bounds = create_bounds(gdf)
    # Save the buffer as bounds
    bounds.to_file("output/well-info.gpkg", layer="bounds", driver="GPKG")

    grid = meshgrid_2d(bounds, 1000)
    xmin, ymin, xmax, ymax = bounds.total_bounds

    size_args = dict(width=grid[0].shape[1], height=grid[0].shape[0])

    _transform = rasterio.transform.from_bounds(xmin, ymax, xmax, ymin, **size_args)

    # Each row of the spreadsheet is a well

    mask = geometry_mask(bounds.geometry, out_shape=grid[0].shape, transform=_transform)

    for name in gdf.iloc[:, 1:]:
        df1 = gdf[["geometry", name]].dropna(subset=[name])

        # Get the formation name
        formation = name
        # Get the xy coordinates of the wells
        xy = list(zip(df1.geometry.x, df1.geometry.y))
        # Get the formation top depths
        tops = df1[name].values

        print(f"Processing {formation} formation")

        interpolator = CloughTocher2DInterpolator(xy, tops, rescale=True)
        Z = interpolator(*grid)

        with rasterio.open(
            f"output/{formation}.tif",
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

    embed()


@app.command("model")
def create_model():
    """Create a geological model from the well data using Loop3D"""
    gdf = read_well_data()
    model = create_geological_model(gdf)

    embed()


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
def build_cross_sections():
    """Create a cross section of the basin between two points, and plot with matplotlib"""
    # Create geometry for the cross section
    for section in sections:
        start, end = section
        line = LineString([start, end])
        transformer = Transformer.from_crs(4326, crs, always_xy=True)
        line_prj = transform(transformer.transform, line)

        # Load the raster data surface-by-surface and interpolate along the cross section
        series = {}

        for file in (here / "output").glob("*.tif"):
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
