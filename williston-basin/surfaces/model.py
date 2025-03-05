from LoopStructural import GeologicalModel
from geopandas import GeoDataFrame
import numpy as N


def create_geological_model(gdf):

    extents = create_model_extents(gdf)

    model = GeologicalModel(*extents)
    return model


def create_model_extents(gdf, z_range=None):
    if z_range is None:
        z_range = [-5000, 1000]

    xy_bounds = gdf.total_bounds
    origin = N.array([xy_bounds[0], xy_bounds[1], z_range[0]])
    extent = N.array([xy_bounds[2], xy_bounds[3], z_range[1]])
    return origin, extent


def create_bounds(gdf):
    buffer = gdf["geometry"].buffer(100000).unary_union.buffer(-90000).simplify(10000)
    return GeoDataFrame(geometry=[buffer], crs=gdf.crs)
