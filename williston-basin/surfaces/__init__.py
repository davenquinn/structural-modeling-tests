from typer import Typer
from pandas import read_csv
from IPython import embed
import geopandas as G

app = Typer()

# Albus equal area projection of the lower 48 states
# Good CRS for the Williston Basin
crs = "EPSG:5069"
# U.S. Survey foot to meter conversion
ft_to_m = 0.3048006096012192

@app.command()
def process_well_data():
    """Ingest well data, find surfaces, and create raster images"""


    df = read_csv("data/Williston_Basin_well_data.csv")
    # Set index to WELL_ID
    df.set_index("WELL_ID", inplace=True)
    # Well data starts at column 7, convert to meters
    df.iloc[:, 6:] *= ft_to_m

    # Convert to GeoDataFrame using LAT and LON columns
    gdf = G.GeoDataFrame(df, geometry=G.points_from_xy(df.LONG, df.LAT, crs="EPSG:4326"))
    gdf = gdf.iloc[:, 6:]
    # Move geometry to the beginning, and keep only formation top depths
    gdf = gdf[["geometry"] + [col for col in gdf.columns if (col != "geometry" and "TOP" in col)]]

    well_info = gdf.copy()
    max_depth = well_info.iloc[:,1:].min(axis=1)
    n_surfaces = well_info.iloc[:,1:].count(axis=1)
    well_info = well_info[["geometry"]].assign(max_depth=max_depth, n_surfaces=n_surfaces)
    well_info = well_info.to_crs(crs)
    well_info.to_file("data/well-info.gpkg", driver="GPKG")


    # Each row of the spreadsheet is a well
    embed()

if __name__ == "__main__":
    app()
