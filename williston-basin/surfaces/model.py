from LoopStructural import GeologicalModel
from geopandas import GeoDataFrame
import pandas
from pandas import DataFrame
import numpy as N
from LoopStructural.datasets import load_claudius
from LoopStructural.visualisation import Loop3DView
from IPython import embed

def create_geological_model(gdf):

    extents = create_model_extents(gdf)

    model = GeologicalModel(*extents)
    return model


def create_model_extents(gdf, z_range=None):
    if z_range is None:
        z_range = [-5000, 1000]

    xy_bounds = gdf.total_bounds
    origin = N.array([xy_bounds[0], xy_bounds[1], z_range[0] * 100])
    extent = N.array([xy_bounds[2], xy_bounds[3], z_range[1] * 100])
    return origin, extent


def create_model_constraints(gdf):
    # Make well surfaces into xyz constraint

    # Create an empty DataFrame with X,Y,Z,strat_name columns
    df = None

    frames = []
    units = dict()
    for ix, name in enumerate(gdf.iloc[:, 1:]):
        # Get picks for each formation in the geodataframe
        df1 = gdf[["geometry", name]].dropna(subset=[name])

        val = -ix
        dfa = DataFrame(
            {
                "X": df1.geometry.x,
                "Y": df1.geometry.y,
                "Z": df1[name] * 100,
                "val": val,
                "unit_name": name,
                "feature_name": "main",
            }
        )
        dfa.set_index("unit_name", append=True, inplace=True)
        frames.append(dfa)

        min = val - 1
        if ix == len(gdf.columns) - 2:
            min = -N.inf

        units[name] = {
            "max": val,
            "min": min,
            "id": ix,
        }
    # Stack the dataframes
    return pandas.concat(frames), dict(main=units)


def create_bounds(gdf):
    buffer = gdf["geometry"].buffer(100000).unary_union.buffer(-90000).simplify(10000)
    return GeoDataFrame(geometry=[buffer], crs=gdf.crs)


def run_loop_demo():
    """Run a Loop3D modeling demo"""
    data, bb = load_claudius()
    data = data.reset_index()

    data.loc[:, "val"] *= -1
    data.loc[:, ["nx", "ny", "nz"]] *= -1

    data.loc[792, "feature_name"] = "strati2"
    data.loc[792, ["nx", "ny", "nz"]] = [0, 0, 1]
    data.loc[792, "val"] = 0

    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)

    strati2 = model.create_and_add_foliation(
        "strati2",
        interpolatortype="FDI",
        nelements=1e5,
    )
    uc = model.add_unconformity(strati2, 1)

    strati = model.create_and_add_foliation(
        "strati",
        interpolatortype="FDI",
        nelements=1e5,
    )

    stratigraphic_column = {}
    stratigraphic_column["strati2"] = {}
    stratigraphic_column["strati2"]["unit1"] = {"min": 1, "max": 10, "id": 0}
    stratigraphic_column["strati"] = {}
    stratigraphic_column["strati"]["unit2"] = {"min": -60, "max": 0, "id": 1}
    stratigraphic_column["strati"]["unit3"] = {"min": -250, "max": -60, "id": 2}
    stratigraphic_column["strati"]["unit4"] = {"min": -330, "max": -250, "id": 3}
    stratigraphic_column["strati"]["unit5"] = {"min": -N.inf, "max": -330, "id": 4}

    model.set_stratigraphic_column(stratigraphic_column)

    viewer = Loop3DView(model)
    viewer.plot_block_model()
    viewer.show(interactive=True)
