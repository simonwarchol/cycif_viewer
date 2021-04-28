from sklearn.neighbors import BallTree
import numpy as np
import pandas as pd
from PIL import ImageColor
import json
import os
from pathlib import Path
from ome_types import from_xml
from cycif_viewer import config_json_path, data_path
from cycif_viewer.server.utils import pyramid_assemble
from cycif_viewer.server.models import database_model
import dateutil.parser
import time
import pickle
import tifffile as tf
import re
import zarr
from dask import dataframe as dd
import cv2

ball_tree = None
database = None
source = None
config = None
seg = None
channels = None
metadata = None


def init(datasource_name):
    load_ball_tree(datasource_name)


def load_datasource(datasource_name, reload=False):
    global datasource
    global source
    global config
    global seg
    global channels
    global metadata
    if source is datasource_name and datasource is not None and reload is False:
        return
    load_config(datasource_name)
    if reload:
        load_ball_tree(datasource_name, reload=reload)
    csvPath = Path(config[datasource_name]['featureData'][0]['src'])
    print("Loading csv data.. (this can take some time)")
    datasource = pd.read_csv(csvPath)
    datasource['id'] = datasource.index
    datasource = datasource.replace(-np.Inf, 0)
    source = datasource_name
    print("Loading segmentation.")
    if config[datasource_name]['segmentation'].endswith('.zarr'):
        seg = zarr.load(config[datasource_name]['segmentation'])
    else:
        seg_io = tf.TiffFile(config[datasource_name]['segmentation'], is_ome=False)
        seg = zarr.open(seg_io.series[0].aszarr())
    channel_io = tf.TiffFile(config[datasource_name]['channelFile'], is_ome=False)
    print("Loading image descriptions.")
    try:
        xml = channel_io.pages[0].tags['ImageDescription'].value
        metadata = from_xml(xml).images[0].pixels
    except:
        metadata = {}
    channels = zarr.open(channel_io.series[0].aszarr())
    print("Data loading done.")


def load_config(datasource_name):
    global config

    with open(config_json_path, "r+") as configJson:
        config = json.load(configJson)
        updated = False
        # Update Feature SRC
        original = config[datasource_name]['featureData'][0]['src']
        config[datasource_name]['featureData'][0]['src'] = original.replace('static/data', 'cycif_viewer/data')
        csvPath = config[datasource_name]['featureData'][0]['src']
        if Path(csvPath).exists() is False:
            if Path('.' + csvPath).exists():
                csvPath = '.' + csvPath
        config[datasource_name]['featureData'][0]['src'] = str(Path(csvPath))
        if original != config[datasource_name]['featureData'][0]['src']:
            updated = True
        try:
            original = config[datasource_name]['segmentation']
            config[datasource_name]['segmentation'] = original.replace('static/data', 'cycif_viewer/data')
            if original != config[datasource_name]['segmentation']:
                updated = True

        except KeyError:
            print(datasource_name, 'is  missing segmentation')

        if updated:
            configJson.seek(0)  # <--- should reset file position to the beginning.
            json.dump(config, configJson, indent=4)
            configJson.truncate()


def load_ball_tree(datasource_name_name, reload=False):
    global ball_tree
    global datasource
    global config
    if datasource_name_name != source:
        load_datasource(datasource_name_name)
    pickled_kd_tree_path = str(
        Path(
            os.path.join(os.getcwd())) / data_path / datasource_name_name / "ball_tree.pickle")
    if os.path.isfile(pickled_kd_tree_path) and reload is False:
        print("Pickled KD Tree Exists, Loading")
        ball_tree = pickle.load(open(pickled_kd_tree_path, "rb"))
        print("Pickled KD Tree Loaded.")
    else:
        print("Creating KD Tree.")
        xCoordinate = config[datasource_name_name]['featureData'][0]['xCoordinate']
        yCoordinate = config[datasource_name_name]['featureData'][0]['yCoordinate']
        csvPath = Path(config[datasource_name_name]['featureData'][0]['src'])
        raw_data = pd.read_csv(csvPath)
        points = pd.DataFrame({'x': raw_data[xCoordinate], 'y': raw_data[yCoordinate]})
        ball_tree = BallTree(points, metric='euclidean')
        pickle.dump(ball_tree, open(pickled_kd_tree_path, 'wb'))
        print('Creating KD Tree done.')


def query_for_closest_cell(x, y, datasource_name):
    global datasource
    global source
    global ball_tree
    if datasource_name != source:
        load_ball_tree(datasource_name)
    distance, index = ball_tree.query([[x, y]], k=1)
    if distance == np.inf:
        return {}
    #         Nothing found
    else:
        try:
            row = datasource.iloc[index[0]]
            obj = row.to_dict(orient='records')[0]
            if 'phenotype' not in obj:
                obj['phenotype'] = ''
            return obj
        except:
            return {}


def get_row(row, datasource_name):
    global database
    global source
    global ball_tree
    if datasource_name != source:
        load_ball_tree(datasource_name)
    obj = database.loc[[row]].to_dict(orient='records')[0]
    obj['id'] = row
    return obj


def get_channel_names(datasource_name, shortnames=True):
    global datasource
    global source
    if datasource_name != source:
        load_ball_tree(datasource_name)
    if shortnames:
        channel_names = [channel['name'] for channel in config[datasource_name]['imageData'][1:]]
    else:
        channel_names = [channel['fullname'] for channel in config[datasource_name]['imageData'][1:]]
    return channel_names


def get_channel_cells(datasource_name, channels):
    global datasource
    global source
    global ball_tree

    range = [0, 65536]

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)

    query_string = ''
    for c in channels:
        if query_string != '':
            query_string += ' and '
        query_string += str(range[0]) + ' < ' + c + ' < ' + str(range[1])
    if query_string == None or query_string == "":
        return []
    query = datasource.query(query_string)[['id']].to_dict(orient='records')
    return query


def get_phenotype_description(datasource):
    try:
        data = ''
        csvPath = config[datasource]['featureData'][0]['phenotypeData']
        if os.path.isfile(csvPath):
            data = pd.read_csv(csvPath)
            data = data.to_numpy().tolist()
            # data = data.to_json(orient='records', lines=True)
        return data;
    except KeyError:
        return ''
    except TypeError:
        return ''


def get_phenotype_column_name(datasource):
    try:
        return config[datasource]['featureData'][0]['phenotype']
    except KeyError:
        return ''
    except TypeError:
        return ''


def get_cells_phenotype(datasource_name):
    global datasource
    global source
    global ball_tree

    range = [0, 65536]

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)

    try:
        phenotype_field = config[datasource_name]['featureData'][0]['phenotype']
    except KeyError:
        phenotype_field = 'phenotype'
    except TypeError:
        phenotype_field = 'phenotype'

    query = datasource[['id', phenotype_field]].to_dict(orient='records')
    return query


def get_phenotypes(datasource_name):
    global datasource
    global source
    global config
    try:
        phenotype_field = config[datasource_name]['featureData'][0]['phenotype']
    except KeyError:
        phenotype_field = 'phenotype'
    except TypeError:
        phenotype_field = 'phenotype'

    if datasource_name != source:
        load_ball_tree(datasource_name)
    if phenotype_field in datasource.columns:
        return sorted(datasource[phenotype_field].unique().tolist())
    else:
        return ['']


def get_neighborhood(x, y, datasource_name, r=100, fields=None):
    global database
    global datasource
    global source
    global ball_tree
    if datasource_name != source:
        load_datasource(datasource_name)
    index = ball_tree.query_radius([[x, y]], r=r)
    neighbors = index[0]
    try:
        if fields and len(fields) > 0:
            fields.append('id') if 'id' not in fields else fields
            if len(fields) > 1:
                neighborhood = datasource.iloc[neighbors][fields].to_dict(orient='records')
            else:
                neighborhood = datasource.iloc[neighbors][fields].to_dict()
        else:
            neighborhood = datasource.iloc[neighbors].to_dict(orient='records')

        return neighborhood
    except:
        return {}


def get_neighborhood_for_spat_corr(x, y, datasource_name, r=100, fields=None):
    global database
    global datasource
    global source
    global ball_tree
    if datasource_name != source:
        load_datasource(datasource_name)
    index = ball_tree.query_radius([[x, y]], r=r)
    neighbors = index[0]
    try:
        if fields and len(fields) > 0:
            fields.append('id') if 'id' not in fields else fields
            if len(fields) > 1:
                neighborhood = datasource.iloc[neighbors][fields].to_dict(orient='records')
            else:
                neighborhood = datasource.iloc[neighbors][fields].to_dict()
        else:
            neighborhood = datasource.iloc[neighbors].to_dict(orient='records')

        print(datasource)
        return neighborhood
    except:
        return {}


def get_number_of_cells_in_circle(x, y, datasource_name, r):
    global source
    global ball_tree
    if datasource_name != source:
        load_ball_tree(datasource_name)
    index = ball_tree.query_radius([[x, y]], r=r)
    try:
        return len(index[0])
    except:
        return 0


def get_color_scheme(datasource_name, refresh, label_field='phenotype'):
    color_scheme_path = str(
        Path(os.path.join(os.getcwd())) / data_path / datasource_name / str(
            label_field + "_color_scheme.pickle"))
    if refresh == False:
        if os.path.isfile(color_scheme_path):
            print("Color Scheme Exists, Loading")
            color_scheme = pickle.load(open(color_scheme_path, "rb"))
            return color_scheme
    if label_field == 'phenotype':
        labels = get_phenotypes(datasource_name)
        print(labels)
    labels.append('SelectedCluster')
    color_scheme = {}
    colors = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf", "#808080", "#7A4900"]
    for i in range(len(labels)):
        color_scheme[str(labels[i])] = {}
        color_scheme[str(labels[i])]['rgb'] = list(ImageColor.getcolor(colors[i], "RGB"))
        color_scheme[str(labels[i])]['hex'] = colors[i]

    pickle.dump(color_scheme, open(color_scheme_path, 'wb'))
    return color_scheme


def get_rect_cells(datasource_name, rect, channels):
    global datasource
    global source
    global ball_tree

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)

    # Query
    index = ball_tree.query_radius([[rect[0], rect[1]]], r=rect[2])
    print('Query size:', len(index[0]))
    neighbors = index[0]
    try:
        neighborhood = []
        for neighbor in neighbors:
            row = datasource.iloc[[neighbor]]
            obj = row.to_dict(orient='records')[0]
            if 'phenotype' not in obj:
                obj['phenotype'] = ''
            neighborhood.append(obj)
        return neighborhood
    except:
        return {}


def get_gated_cells(datasource_name, gates):
    global datasource
    global source
    global ball_tree

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)

    query_string = ''
    for key, value in gates.items():
        if query_string != '':
            query_string += ' and '
        query_string += str(value[0]) + ' < ' + key + ' < ' + str(value[1])
    if query_string == None or query_string == "":
        return []
    query = datasource.query(query_string)[['id']].to_dict(orient='records')
    return query


def download_gating_csv(datasource_name, gates, channels):
    global datasource
    global source
    global ball_tree

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)

    query_string = ''
    columns = []
    for key, value in gates.items():
        columns.append(key)
        if query_string != '':
            query_string += ' and '
        query_string += str(value[0]) + ' < ' + key + ' < ' + str(value[1])
    ids = datasource.query(query_string)[['id']].to_numpy().flatten()
    if 'idField' in config[datasource_name]['featureData'][0]:
        idField = config[datasource_name]['featureData'][0]['idField']
    else:
        idField = "CellID"
    columns.append(idField)

    csv = datasource.copy()

    csv[idField] = datasource['id']
    for channel in channels:
        if channel in gates:
            csv.loc[csv[idField].isin(ids), key] = 1
            csv.loc[~csv[idField].isin(ids), key] = 0
        else:
            csv[channel] = 0

    return csv


def download_gates(datasource_name, gates, channels):
    global datasource
    global source
    global ball_tree

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)
    arr = []
    for key, value in channels.items():
        arr.append([key, value[0], value[1]])
    csv = pd.DataFrame(arr)
    csv.columns = ['channel', 'gate_start', 'gate_end']
    csv['gate_active'] = False
    for channel in gates:
        csv.loc[csv['channel'] == channel, 'gate_active'] = True
        csv.loc[csv['channel'] == channel, 'gate_start'] = gates[channel][0]
        csv.loc[csv['channel'] == channel, 'gate_end'] = gates[channel][1]
    return csv


def get_datasource_description(datasource_name):
    global datasource
    global source
    global ball_tree

    # Load if not loaded
    if datasource_name != source:
        load_ball_tree(datasource_name)
    description = datasource.describe(percentiles=[.005, .01, .25, .5, .75, .95, .99, .995]).to_dict()
    for column in description:
        col = datasource[column]
        col = col[(col >= description[column]['1%']) & (col <= description[column]['99%'])]
        col = col.to_numpy()
        [hist, bin_edges] = np.histogram(col, bins=25, density=True)
        midpoints = (bin_edges[1:] + bin_edges[:-1]) / 2
        description[column]['histogram'] = {}
        dat = []
        for i in range(len(hist)):
            obj = {}
            obj['x'] = midpoints[i]
            obj['y'] = hist[i]
            dat.append(obj)
        description[column]['histogram'] = dat
    return description


def spatial_corr (adata, raw=False, log=False, threshold=None, x_coordinate='X_centroid',y_coordinate='Y_centroid',
                  marker=None, k=500, label='spatial_corr', index='id', channels=[]):
    global datasource
    global source
    global ball_tree
    global config

    """
    Parameters
    ----------
    adata : TYPE
        DESCRIPTION.
    raw : TYPE, optional
        DESCRIPTION. The default is False.
    log : TYPE, optional
        DESCRIPTION. The default is False.
    threshold : TYPE, optional
        DESCRIPTION. The default is None.
    x_coordinate : TYPE, optional
        DESCRIPTION. The default is 'X_centroid'.
    y_coordinate : TYPE, optional
        DESCRIPTION. The default is 'Y_centroid'.
    marker : TYPE, optional
        DESCRIPTION. The default is None.
    k : TYPE, optional
        DESCRIPTION. The default is 500.
    label : TYPE, optional
        DESCRIPTION. The default is 'spatial_corr'.
    Returns
    -------
    corrfunc : TYPE
        DESCRIPTION.
    Example
    -------
    adata = spatial_corr (adata, threshold=0.5, x_coordinate='X_position',y_coordinate='Y_position',marker=None)
    """
    # Reset some vars (hardcoded for now)
    # adata = pd.DataFrame(datasource)
    # x_coordinate = config[source]['featureData'][0]['xCoordinate']
    # y_coordinate = config[source]['featureData'][0]['yCoordinate']
    # index = config[source]['featureData'][0]['idField']
    # channels = [d['fullname'] for d in config[source]['imageData']][1:]

    #Start
    bdata = adata.copy()
    bdata_features = channels.copy()
    print('Input shape', bdata[bdata_features].shape)
    bdata_features.append(index)
    # Create a DataFrame with the necessary information
    data = pd.DataFrame({'x': bdata[x_coordinate], 'y': bdata[y_coordinate]})
    # user defined expression matrix
    exp = pd.DataFrame(bdata[bdata_features], index=bdata[index], columns=channels)
    # log the data if needed
    if log is True:
        exp = np.log1p(exp)
    # set a threshold if needed
    if threshold is not None:
        exp[exp >= threshold] = 1
        exp[exp < threshold] = 0
    # subset markers if needed
    if marker is not None:
        if isinstance(marker, str):
            marker = [marker]
        exp = exp[marker]
    # find the nearest neighbours
    tree = BallTree(data, leaf_size=2)
    dist, ind = tree.query(data, k=k, return_distance=True)
    neighbours = pd.DataFrame(ind, index=bdata[index])
    # find the mean dist
    rad_approx = np.mean(dist, axis=0)
    # Calculate the correlation
    mean = np.mean(exp).values
    std = np.std(exp).values
    A = (exp - mean) / std
    def corrfunc (marker, A, neighbours, ind):
        print('Processing ' + str(marker))
        # Map phenotype
        ind_values = dict(zip(list(range(len(ind))), A[marker])) # Used for mapping
        # Loop through (all functionized methods were very slow)
        neigh = neighbours.copy()
        for i in neigh.columns:
            neigh[i] = neigh[i].dropna().map(ind_values, na_action='ignore')
        # multiply the matrices
        Y = neigh.T * A[marker]
        corrfunc = np.mean(Y, axis=1)
        # return
        return corrfunc
    # apply function to all markers    # Create lamda function
    r_corrfunc = lambda x: corrfunc(marker=x, A=A, neighbours=neighbours, ind=ind)
    all_data = list(map(r_corrfunc, exp.columns)) # Apply function
    # Merge all the results into a single dataframe
    df = pd.concat(all_data, axis=1)
    print(all_data)
    df.columns = exp.columns
    df['distance'] = rad_approx
    # add it to anndata object
    # adata.uns[label] = df
    print('Output shape', df.shape)
    # return
    return df


def generate_zarr_png(datasource_name, channel, level, tile):
    if config is None:
        load_datasource(datasource_name)
    global channels
    global seg
    [tx, ty] = tile.replace('.png', '').split('_')
    tx = int(tx)
    ty = int(ty)
    level = int(level)
    tile_width = config[datasource_name]['tileWidth']
    tile_height = config[datasource_name]['tileHeight']
    ix = tx * tile_width
    iy = ty * tile_height
    segmentation = False
    try:
        channel_num = int(re.match(r".*_(\d*)$", channel).groups()[0])
    except AttributeError:
        segmentation = True
    if segmentation:
        tile = seg[level][iy:iy + tile_height, ix:ix + tile_width]

        tile = tile.view('uint8').reshape(tile.shape + (-1,))[..., [0, 1, 2]]
        tile = np.append(tile, np.zeros((tile.shape[0], tile.shape[1], 1), dtype='uint8'), axis=2)
    else:
        if isinstance(channels, zarr.Array):
            tile = channels[channel_num, iy:iy + tile_height, ix:ix + tile_width]
        else:
            tile = channels[level][channel_num, iy:iy + tile_height, ix:ix + tile_width]
            tile = tile.astype('uint16')

    # tile = np.ascontiguousarray(tile, dtype='uint32')
    # png = tile.view('uint8').reshape(tile.shape + (-1,))[..., [2, 1, 0]]
    return tile


def get_ome_metadata(datasource_name):
    if config is None:
        load_datasource(datasource_name)
    global metadata
    return metadata


def convertOmeTiff(filePath, channelFilePath=None, dataDirectory=None, isLabelImg=False):
    channel_info = {}
    channelNames = []
    if isLabelImg == False:
        channel_io = tf.TiffFile(str(filePath), is_ome=False)
        channels = zarr.open(channel_io.series[0].aszarr())
        if isinstance(channels, zarr.Array):
            channel_info['maxLevel'] = 1
            chunks = channels.chunks
            shape = channels.shape
        else:
            channel_info['maxLevel'] = len(channels)
            shape = channels[0].shape
            chunks = (1, 1024, 1024)
        chunks = (chunks[-2], chunks[-1])
        channel_info['tileHeight'] = chunks[0]
        channel_info['tileWidth'] = chunks[1]
        channel_info['height'] = shape[1]
        channel_info['width'] = shape[2]
        channel_info['num_channels'] = shape[0]
        for i in range(shape[0]):
            channelName = re.sub(r'\.ome|\.tiff|\.tif|\.png', '', filePath.name) + "_" + str(i)
            channelNames.append(channelName)
        channel_info['channel_names'] = channelNames
        return channel_info
    else:
        channel_io = tf.TiffFile(str(channelFilePath), is_ome=False)
        channels = zarr.open(channel_io.series[0].aszarr())
        directory = Path(dataDirectory + "/" + filePath.name)
        args = {}
        args['in_paths'] = [Path(filePath)]
        args['out_path'] = directory
        args['is_mask'] = True
        pyramid_assemble.main(py_args=args)

        return {'segmentation': str(directory)}


def save_dot(datasource_name, dot):
    database_model.create_or_update(database_model.Dot, id=dot['id'], datasource=datasource_name, group=dot['group'],
                                    name=dot['name'], description=dot['description'], shape_type=dot['shape_type'],
                                    shape_info=dot['shape_info'], cell_ids=dot['cell_ids'],
                                    date=dateutil.parser.parse(dot['date']), image_data=dot['image_data'],
                                    viewer_info=dot['viewer_info'], channel_info=dot['channel_info'])


def load_dots(datasource_name):
    dots = database_model.get_all(database_model.Dot, datasource=datasource_name)
    print(dots)
    return dots


def delete_dot(datasource_name, id):
    database_model.edit(database_model.Dot, id, 'is_deleted', True)
    return True
