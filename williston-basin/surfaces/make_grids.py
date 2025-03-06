from pathlib import Path
import rasterio
import numpy as N

ft_to_m = 0.3048006096012192


def make_grids_from_ascii():
    """Make ASCII grids into GeoTIFFs."""

    here = Path(__file__).parent.parent
    # Get the data directory
    data_dir = here / "data" / "grids_horizons"
    # Get the output directory
    out_dir = here / "output" / "grids"

    out_dir.mkdir(exist_ok=True)

    for grid in data_dir.glob("*.asc"):

        out_file = out_dir / (grid.stem + ".tif")
        # Convert the ASCII grid to a GeoTIFF
        with rasterio.open(grid) as src:
            profile = src.profile
            profile.update(
                driver="COG",
                count=1,
                compress="lzw",
                nodata=None,
            )
            with rasterio.open(out_file, "w", **profile) as dst:
                band = src.read(1)
                band[band == -9999] = N.nan
                dst.write(band * -ft_to_m, 1)
