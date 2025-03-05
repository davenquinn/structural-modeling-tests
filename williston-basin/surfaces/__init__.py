from typer import Typer
from pandas import read_csv
from IPython import embed
import geopandas as G
from numpy import meshgrid, linspace, nan
from scipy.interpolate import CloughTocher2DInterpolator
import rasterio
from rasterio.features import geometry_mask

app = Typer()

# Albus equal area projection of the lower 48 states
# Good CRS for the Williston Basin
crs = "EPSG:5069"
# U.S. Survey foot to meter conversion
ft_to_m = 0.3048006096012192


@app.command("build")
def process_well_data():
    """Ingest well data, find surfaces, and create raster images"""

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

    gdf = gdf.to_crs(crs)

    well_info = gdf.copy()
    max_depth = well_info.iloc[:, 1:].min(axis=1)
    n_surfaces = well_info.iloc[:, 1:].count(axis=1)
    well_info = well_info[["geometry"]].assign(
        max_depth=max_depth, n_surfaces=n_surfaces
    )

    well_info.to_file("output/well-info.gpkg", layer="metadata", driver="GPKG")

    # Create a buffer around the wells to form a rough basin outline
    buffer = (
        well_info["geometry"].buffer(100000).unary_union.buffer(-90000).simplify(10000)
    )
    # Save the buffer as bounds
    bounds = G.GeoDataFrame(geometry=[buffer], crs=crs)
    bounds.to_file("output/well-info.gpkg", layer="bounds", driver="GPKG")

    grid = meshgrid_2d(bounds, 1000)
    xmin, ymin, xmax, ymax = bounds.total_bounds

    size_args = dict(width=grid[0].shape[1], height=grid[0].shape[0])

    transform = rasterio.transform.from_bounds(xmin, ymax, xmax, ymin, **size_args)

    # Each row of the spreadsheet is a well

    mask = geometry_mask(bounds.geometry, out_shape=grid[0].shape, transform=transform)

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
            transform=transform,
            dtype=Z.dtype,
        ) as dst:
            Z[mask] = nan
            dst.write(Z, 1)

    embed()


def meshgrid_2d(bounds, n_samples):
    # Create a regular grid of points within the bounds
    xmin, ymin, xmax, ymax = bounds.total_bounds
    aspect_ratio = (xmax - xmin) / (ymax - ymin)
    nsx, nsy = n_samples, int(n_samples / aspect_ratio)
    if aspect_ratio > 1:
        nsx, nsy = nsy, nsx

    return meshgrid(linspace(xmin, xmax, nsx), linspace(ymin, ymax, nsy))


if __name__ == "__main__":
    app()
