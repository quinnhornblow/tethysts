"""


"""
import io
import os
import numpy as np
# import requests
import xarray as xr
import pandas as pd
import orjson
from datetime import datetime
import zstandard as zstd
import pickle
import copy
# import boto3
import botocore
from time import sleep
from shapely.geometry import shape, Polygon, Point
from shapely.strtree import STRtree
from typing import Optional, List, Any, Union
from scipy import spatial
# import tethys_data_models as tdm
import pathlib
# from functools import partial
from pydantic import HttpUrl
# import shutil
# import gzip
from hdf5tools import H5
import s3tethys
# import smart_open
# import psutil
from pprint import pprint

pd.options.display.max_columns = 10

##############################################
### Reference objects

b2_public_key_pattern = '{base_url}/{bucket}/{obj_key}'
contabo_public_key_pattern = '{base_url}:{bucket}/{obj_key}'
public_remote_key = 'https://b2.tethys-ts.xyz/file/tethysts/tethys/public_remotes_v4.json.zst'

local_results_name = '{ds_id}/{version_date}/{stn_id}/{chunk_id}.{chunk_hash}.results.h5'

s3_url_base = 's3://{bucket}/{key}'

##############################################
### Helper functions


def update_nested(in_dict, ds_id, version_date, value):
    """

    """
    if ds_id in in_dict:
        in_dict[ds_id][version_date] = value
    else:
        in_dict.update({ds_id: {version_date: value}})


def make_run_date_key(run_date=None):
    """

    """
    if run_date is None:
        run_date = pd.Timestamp.today(tz='utc')
        run_date_key = run_date.strftime('%Y%m%dT%H%M%SZ')
    elif isinstance(run_date, pd.Timestamp):
        run_date_key = run_date.strftime('%Y%m%dT%H%M%SZ')
    elif isinstance(run_date, str):
        run_date1 = pd.Timestamp(run_date).tz_localize(None)
        run_date_key = run_date1.strftime('%Y%m%dT%H%M%SZ')
    else:
        raise TypeError('run_date must be None, Timestamp, or a string representation of a timestamp')

    return run_date_key


def create_public_s3_url(base_url, bucket, obj_key):
    """
    This should be updated as more S3 providers are added!
    """
    if 'contabo' in base_url:
        key = contabo_public_key_pattern.format(base_url=base_url.rstrip('/'), bucket=bucket, obj_key=obj_key)
    else:
        key = b2_public_key_pattern.format(base_url=base_url.rstrip('/'), bucket=bucket, obj_key=obj_key)

    return key


# class ResponseStream(object):
#     """
#     In many applications, you'd like to access a requests response as a file-like object, simply having .read(), .seek(), and .tell() as normal. Especially when you only want to partially download a file, it'd be extra convenient if you could use a normal file interface for it, loading as needed.

# This is a wrapper class for doing that. Only bytes you request will be loaded - see the example in the gist itself.

# https://gist.github.com/obskyr/b9d4b4223e7eaf4eedcd9defabb34f13
#     """
#     def __init__(self, request_iterator):
#         self._bytes = BytesIO()
#         self._iterator = request_iterator

#     def _load_all(self):
#         self._bytes.seek(0, SEEK_END)
#         for chunk in self._iterator:
#             self._bytes.write(chunk)

#     def _load_until(self, goal_position):
#         current_position = self._bytes.seek(0, SEEK_END)
#         while current_position < goal_position:
#             try:
#                 current_position += self._bytes.write(next(self._iterator))
#             except StopIteration:
#                 break

#     def tell(self):
#         return self._bytes.tell()

#     def read(self, size=None):
#         left_off_at = self._bytes.tell()
#         if size is None:
#             self._load_all()
#         else:
#             goal_position = left_off_at + size
#             self._load_until(goal_position)

#         self._bytes.seek(left_off_at)
#         return self._bytes.read(size)

#     def seek(self, position, whence=SEEK_SET):
#         if whence == SEEK_END:
#             self._load_all()
#         else:
#             self._bytes.seek(position, whence)


def cartesian_product(*arrays):
    la = len(arrays)
    dtype = np.result_type(*arrays)
    arr = np.empty([len(a) for a in arrays] + [la], dtype=dtype)
    for i, a in enumerate(np.ix_(*arrays)):
        arr[...,i] = a
    return arr.reshape(-1, la)


def get_nearest_station(stns, geom_query):
    """

    """
    if isinstance(geom_query, dict):
        geom_query = shape(geom_query)

    geom1 = [shape(s['geometry']) for i, s in stns.items()]
    strtree = STRtree(geom1)
    res_index = strtree.nearest(geom_query)

    stn_ids_list = list(stns.keys())
    stn_id = stn_ids_list[res_index]

    return stn_id


def get_intersected_stations(stns, geom_query):
    """

    """
    if isinstance(geom_query, dict):
        geom_query = shape(geom_query)

    stn_ids_list = list(stns.keys())
    geom1 = [shape(s['geometry']) for i, s in stns.items()]
    strtree = STRtree(geom1)
    res_index = strtree.query(geom_query)

    stn_ids = [stn_ids_list[r] for r in res_index]

    # res_ids = [r.wkb_hex for r in res]

    # stn_id_dict = {shape(s['geometry']).wkb_hex: i for i, s in stns.items()}

    # stn_ids = [stn_id_dict[r] for r in res_ids]

    return stn_ids


def spatial_query(stns: dict,
                  query_geometry: Optional[dict] = None,
                  lat: Optional[float] = None,
                  lon: Optional[float] = None,
                  distance: Optional[float] = None):
    """

    """
    if isinstance(lat, float) and isinstance(lon, float):
        geom_query = Point(lon, lat)
        if isinstance(distance, (int, float)):
            geom_query = geom_query.buffer(distance)
            stn_ids = get_intersected_stations(stns, geom_query)
        else:
            stn_ids = [get_nearest_station(stns, geom_query)]
    elif isinstance(query_geometry, dict):
        geom_query = shape(query_geometry)
        if isinstance(geom_query, Point):
            stn_ids = [get_nearest_station(stns, geom_query)]
        elif isinstance(geom_query, Polygon):
            stn_ids = get_intersected_stations(stns, geom_query)
        else:
            raise ValueError('query_geometry must be a Point or Polygon dict.')
    else:
        stn_ids = None

    return stn_ids


def get_nearest_from_extent(data,
                            query_geometry: Optional[dict] = None,
                            lat: Optional[float] = None,
                            lon: Optional[float] = None):
    """

    """
    ## Prep the query point
    if isinstance(lat, float) and isinstance(lon, float):
        geom_query = Point(lon, lat)
    elif isinstance(query_geometry, dict):
        geom_query = shape(query_geometry)
        if not isinstance(geom_query, Point):
            raise ValueError('query_geometry must be a Point.')
    else:
        raise ValueError('query_geometry or lat/lon must be passed as a Point.')

    ## Prep the input data
    if 'geometry' in data:
        raise NotImplementedError('Need to implement geometry blocks nearest query.')
    else:
        lats = data['lat'].values
        lons = data['lon'].values
        xy = cartesian_product(lons, lats)
        kdtree = spatial.cKDTree(xy)
        dist, index = kdtree.query(geom_query.coords[0])
        lon_n, lat_n = xy[index]

    data1 = data.sel(lon=[lon_n], lat=[lat_n])

    return data1


def read_pkl_zstd(obj, unpickle=False):
    """
    Deserializer from a pickled object compressed with zstandard.

    Parameters
    ----------
    obj : bytes or str
        Either a bytes object that has been pickled and compressed or a str path to the file object.
    unpickle : bool
        Should the bytes object be unpickled or left as bytes?

    Returns
    -------
    Python object
    """
    if isinstance(obj, str):
        with open(obj, 'rb') as p:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(p) as reader:
                obj1 = reader.read()

    elif isinstance(obj, bytes):
        dctx = zstd.ZstdDecompressor()
        obj1 = dctx.decompress(obj)
    else:
        raise TypeError('obj must either be a str path or a bytes object')

    if unpickle:
        obj1 = pickle.loads(obj1)

    return obj1


def read_json_zstd(obj):
    """
    Deserializer from a compressed zstandard json object to a dictionary.

    Parameters
    ----------
    obj : bytes
        The bytes object.

    Returns
    -------
    Dict
    """
    if isinstance(obj, str):
        with open(obj, 'rb') as p:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(p) as reader:
                obj1 = reader.read()
    elif isinstance(obj, bytes):
        dctx = zstd.ZstdDecompressor()
        obj1 = dctx.decompress(obj)
    else:
        raise TypeError('obj must either be a str path or a bytes object')

    dict1 = orjson.loads(obj1)

    return dict1


# def s3_client(connection_config: dict, max_pool_connections: int = 30):
#     """
#     Function to establish a client connection with an S3 account. This can use the legacy connect (signature_version s3) and the curent version.

#     Parameters
#     ----------
#     connection_config : dict
#         A dictionary of the connection info necessary to establish an S3 connection. It should contain service_name, endpoint_url, aws_access_key_id, and aws_secret_access_key. connection_config can also be a URL to a public S3 bucket.
#     max_pool_connections : int
#         The number of simultaneous connections for the S3 connection.

#     Returns
#     -------
#     S3 client object
#     """
#     ## Validate config
#     _ = tdm.base.ConnectionConfig(**connection_config)

#     s3_config = copy.deepcopy(connection_config)

#     if 'config' in s3_config:
#         config0 = s3_config.pop('config')
#         config0.update({'max_pool_connections': max_pool_connections})
#         config1 = boto3.session.Config(**config0)

#         s3_config1 = s3_config.copy()
#         s3_config1.update({'config': config1})

#         s3 = boto3.client(**s3_config1)
#     else:
#         s3_config.update({'config': botocore.config.Config(max_pool_connections=max_pool_connections)})
#         s3 = boto3.client(**s3_config)

#     return s3


# def get_object_s3(obj_key: str, bucket: str, s3: botocore.client.BaseClient = None, connection_config: dict = None, public_url: HttpUrl=None, version_id=None, range_start: int=None, range_end: int=None, chunk_size=524288, counter=5):
#     """
#     General function to get an object from an S3 bucket. One of s3, connection_config, or public_url must be used.

#     Parameters
#     ----------
#     obj_key : str
#         The object key in the S3 bucket.
#     s3 : botocore.client.BaseClient
#         An S3 client object created via the s3_client function.
#     connection_config : dict
#         A dictionary of the connection info necessary to establish an S3 connection. It should contain service_name, s3, endpoint_url, aws_access_key_id, and aws_secret_access_key.
#     public_url : str
#         A URL to a public S3 bucket. This is generally only used for Backblaze object storage.
#     bucket : str
#         The bucket name.
#     counter : int
#         Number of times to retry to get the object.

#     Returns
#     -------
#     bytes
#         bytes object of the S3 object.
#     """
#     counter1 = counter

#     transport_params = {'buffer_size': chunk_size}

#     if isinstance(version_id, str):
#         transport_params['version_id'] = version_id

#     ## Headers
#     headers = {}
#     # Range
#     range_dict = {}

#     if range_start is not None:
#         range_dict['start'] = str(range_start)
#     else:
#         range_dict['start'] = ''

#     if range_end is not None:
#         range_dict['end'] = str(range_end)
#     else:
#         range_dict['end'] = ''

#     ## Get the object
#     while True:
#         try:
#             if isinstance(public_url, str) and (version_id is None):
#                 url = create_public_s3_url(public_url, bucket, obj_key)

#                 if range_dict:
#                     range1 = 'bytes={start}-{end}'.format(**range_dict)
#                     headers['Range'] = range1

#                 file_obj = smart_open.open(url, 'rb', headers=headers, transport_params=transport_params)

#             elif isinstance(s3, botocore.client.BaseClient) or isinstance(connection_config, dict):
#                 if range_dict:
#                     range1 = 'bytes={start}-{end}'.format(**range_dict)
#                     transport_params.update({'client_kwargs': {'S3.Client.get_object': {'Range': range1}}})

#                 if s3 is None:
#                     _ = tdm.base.ConnectionConfig(**connection_config)

#                     s3 = s3_client(connection_config)

#                 s3_url = s3_url_base.format(bucket=bucket, key=obj_key)
#                 transport_params['client'] = s3

#                 file_obj = smart_open.open(s3_url, 'rb', transport_params=transport_params)

#             else:
#                 raise TypeError('One of s3, connection_config, or public_url needs to be correctly defined.')

#             break
#         except:
#             # print(traceback.format_exc())
#             if counter1 == 0:
#                 # raise ValueError('Could not properly download the object after several tries')
#                 print('Object could not be downloaded.')
#                 return None
#             else:
#                 # print('Could not properly extract the object; trying again in 5 seconds')
#                 counter1 = counter1 - 1
#                 sleep(3)

#     return file_obj


def chunk_filters(results_chunks, stn_ids, time_interval=None, from_date=None, to_date=None, heights=None, bands=None, from_mod_date=None, to_mod_date=None):
    """

    """
    ## Stations filter
    rc2 = copy.deepcopy([rc for rc in results_chunks if rc['station_id'] in stn_ids])
    first_one = rc2[0]

    ## Temporal filters
    if isinstance(from_date, (str, pd.Timestamp, datetime)) and ('chunk_day' in first_one):
        from_date1 = int(pd.Timestamp(from_date).timestamp()/60/60/24)
        rc2 = [rc for rc in rc2 if (rc['chunk_day'] + time_interval) >= from_date1]

    if len(rc2) == 0:
        return rc2

    if isinstance(to_date, (str, pd.Timestamp, datetime)) and ('chunk_day' in first_one):
        to_date1 = int(pd.Timestamp(to_date).timestamp()/60/60/24)
        rc2 = [rc for rc in rc2 if rc['chunk_day'] <= to_date1]

    if len(rc2) == 0:
        return rc2

    if isinstance(from_mod_date, (str, pd.Timestamp, datetime)) and ('modified_date' in first_one):
        from_mod_date1 = pd.Timestamp(from_mod_date)
        rc2 = [rc for rc in rc2 if pd.Timestamp(rc['modified_date']) >= from_mod_date1]

    if len(rc2) == 0:
        return rc2

    if isinstance(to_mod_date, (str, pd.Timestamp, datetime)) and ('modified_date' in first_one):
        to_mod_date1 = pd.Timestamp(to_mod_date)
        rc2 = [rc for rc in rc2 if pd.Timestamp(rc['modified_date']) <= to_mod_date1]

    if len(rc2) == 0:
        return rc2

    ## Heights and bands filter
    if (heights is not None) and ('height' in first_one):
        if isinstance(heights, (int, float)):
            h1 = [int(heights*1000)]
        elif isinstance(heights, list):
            h1 = [int(h*1000) for h in heights]
        else:
            raise TypeError('heights must be an int, float, or list of int/float.')
        rc2 = [rc for rc in rc2 if rc['height'] in h1]

    if len(rc2) == 0:
        return rc2

    if (bands is not None) and ('band' in first_one):
        if isinstance(bands, int):
            b1 = [heights]
        elif isinstance(bands, list):
            b1 = [int(b) for b in bands]
        else:
            raise TypeError('bands must be an int or list of int.')
        rc2 = [rc for rc in rc2 if rc['band'] in b1]

    if len(rc2) == 0:
        return rc2

    ## Sort by mod date
    rc2.sort(key=lambda d: d['modified_date'] if 'modified_date' in d else '1900-01-01')

    return rc2


# def remove_char_dim_names(data):
#     """

#     """
#     for v in data.variables:
#         if 'char_dim_name' in data[v].encoding:
#             _ = data[v].encoding.pop('char_dim_name')

#     return data


# def remove_results_junk(data):
#     """

#     """
#     chunk_vars = [v for v in list(data.variables) if 'chunk' in v]
#     if chunk_vars:
#         data = data.drop_vars(chunk_vars)

#     # crap_vars = [v for v in list(data.variables) if 'string' in v]
#     # if crap_vars:
#     #     data = data.drop_vars(crap_vars)

#     # if 'geometry' in data.dims:
#     #     stn_vars = [v for v in list(data.data_vars) if ('time' not in data[v].dims) and (v not in ['station_id', 'lon', 'lat'])]
#     #     data = data.drop_vars(stn_vars)

#     if 'station_geometry' in data.dims:
#         stn_vars = [d for d in data.variables if 'station_geometry' in data[d].dims]
#         data = data.drop_vars(stn_vars)

#     return data


def result_filters(h5, from_date=None, to_date=None):
    """

    """
    h5 = h5.sel(exclude_coords=['station_geometry', 'chunk_date'])

    ## Time filters
    if isinstance(from_date, (str, pd.Timestamp, datetime)):
        from_date1 = np.datetime64(from_date)
    else:
        from_date1 = None
    if isinstance(to_date, (str, pd.Timestamp, datetime)):
        to_date1 = np.datetime64(to_date)
    else:
        to_date1 = None

    if (to_date1 is not None) or (from_date1 is not None):
        h5 = h5.sel({'time': slice(from_date1, to_date1)})

    return h5


# def process_results_output(ts_xr, output='xarray', squeeze_dims=False):
#     """

#     """
#     ## Return
#     if squeeze_dims:
#         ts_xr = ts_xr.squeeze()

#     if output == 'xarray':
#         return ts_xr

#     elif output == 'dict':
#         data_dict = ts_xr.to_dict()

#         return data_dict

#     elif output == 'json':
#         json1 = orjson.dumps(ts_xr.to_dict(), option=orjson.OPT_OMIT_MICROSECONDS | orjson.OPT_SERIALIZE_NUMPY)

#         return json1
#     else:
#         raise ValueError("output must be one of 'xarray', 'dict', or 'json'")


# def read_in_chunks(file_object, chunk_size=524288):
#     while True:
#         data = file_object.read(chunk_size)
#         if not data:
#             break
#         yield data


# def local_file_byte_iterator(path, chunk_size=DEFAULT_BUFFER_SIZE):
#     """given a path, return an iterator over the file
#     that lazily loads the file.
#     https://stackoverflow.com/a/37222446/6952674
#     """
#     path = pathlib.Path(path)
#     with path.open('rb') as file:
#         reader = partial(file.read1, DEFAULT_BUFFER_SIZE)
#         file_iterator = iter(reader, bytes())
#         for chunk in file_iterator:
#             yield from chunk


# def stream_to_file(file_obj, file_path, chunk_size=524288):
#     """

#     """
#     file_path1 = pathlib.Path(file_path)
#     file_path1.parent.mkdir(parents=True, exist_ok=True)

#     with open(file_path1, 'wb') as f:
#         chunk = file_obj.read(chunk_size)
#         while chunk:
#             f.write(chunk)
#             chunk = file_obj.read(chunk_size)


# def decompress_stream_to_file(file_obj, file_path, chunk_size=524288):
#     """

#     """
#     file_path1 = pathlib.Path(file_path)
#     file_path1.parent.mkdir(parents=True, exist_ok=True)

#     if file_path1.suffix == '.zst':
#         file_path2 = file_path1.stem
#         dctx = zstd.ZstdDecompressor()

#         with open(file_path2, 'wb') as f:
#             dctx.copy_stream(file_obj, f, read_size=chunk_size, write_size=chunk_size)

#     elif file_path1.suffix == '.gz':
#         file_path2 = file_path1.stem

#         with gzip.open(file_obj, 'rb') as s_file, open(file_path2, 'wb') as d_file:
#             shutil.copyfileobj(s_file, d_file, chunk_size)

#     else:
#         file_path2 = file_path1
#         stream_to_file(file_obj, file_path2, chunk_size)

#     return str(file_path2)


# def decompress_stream_to_object(file_obj, compression, chunk_size=524288):
#     """

#     """
#     b1 = BytesIO()

#     if compression == 'zstd':
#         dctx = zstd.ZstdDecompressor()

#         with open(b1, 'wb') as f:
#             dctx.copy_stream(file_obj, f, read_size=chunk_size, write_size=chunk_size)

#     elif compression == '.gz':

#         with gzip.open(file_obj, 'rb') as s_file, open(b1, 'wb') as d_file:
#             shutil.copyfileobj(s_file, d_file, chunk_size)

#     else:
#         with open(b1, 'wb') as f:
#             chunk = file_obj.read(chunk_size)
#             while chunk:
#                 f.write(chunk)
#                 chunk = file_obj.read(chunk_size)

#     return b1


# def url_stream_to_file(url, file_path, decompress=False, chunk_size=524288):
#     """

#     """
#     file_path1 = pathlib.Path(file_path)
#     if file_path1.is_dir():
#         file_name = url.split('/')[-1]
#         file_path2 = str(file_path1.joinpath(file_name))
#     else:
#         file_path2 = file_path

#     base_path = os.path.split(file_path2)[0]
#     os.makedirs(base_path, exist_ok=True)

#     counter = 4
#     while True:
#         try:
#             with requests.get(url, stream=True, timeout=300) as r:
#                 r.raise_for_status()
#                 stream = ResponseStream(r.iter_content(chunk_size))

#                 if decompress:
#                     if str(file_path2).endswith('.zst'):
#                         file_path2 = os.path.splitext(file_path2)[0]
#                         dctx = zstd.ZstdDecompressor()

#                         with open(file_path2, 'wb') as f:
#                             dctx.copy_stream(stream, f, read_size=chunk_size, write_size=chunk_size)

#                     elif str(file_path2).endswith('.gz'):
#                         file_path2 = os.path.splitext(file_path2)[0]

#                         with gzip.open(stream, 'rb') as s_file, open(file_path2, 'wb') as d_file:
#                             shutil.copyfileobj(s_file, d_file, chunk_size)

#                     else:
#                         with open(file_path2, 'wb') as f:
#                             chunk = stream.read(chunk_size)
#                             while chunk:
#                                 f.write(chunk)
#                                 chunk = stream.read(chunk_size)
#                 else:
#                     with open(file_path2, 'wb') as f:
#                         chunk = stream.read(chunk_size)
#                         while chunk:
#                             f.write(chunk)
#                             chunk = stream.read(chunk_size)

#                 break

#         except Exception as err:
#             if counter < 1:
#                 raise err
#             else:
#                 counter = counter - 1
#                 sleep(5)

#     return file_path2


# def process_dataset(data, from_date=None, to_date=None):
#     """
#     Stupid xarray being inefficient at parsing file objects...
#     """
#     ## Remove junk fields
#     h1 = H5(data).sel(exclude_coords=['station_geometry', 'chunk_date'])

#     h2 = result_filters(h1, from_date, to_date)

#     data_obj = io.BytesIO()
#     h2.to_hdf5(data_obj)

#     return data_obj


def download_results(chunk: dict, bucket: str, s3: botocore.client.BaseClient = None, connection_config: dict = None, public_url: HttpUrl = None, cache: Union[pathlib.Path] = None, from_date=None, to_date=None, return_raw=False):
    """

    """
    file_obj = s3tethys.get_object_s3(chunk['key'], bucket, s3, connection_config, public_url)

    if isinstance(cache, pathlib.Path):
        chunk_hash = chunk['chunk_hash']
        version_date = pd.Timestamp(chunk['version_date']).strftime('%Y%m%d%H%M%SZ')
        results_file_name = local_results_name.format(ds_id=chunk['dataset_id'], stn_id=chunk['station_id'], chunk_id=chunk['chunk_id'], version_date=version_date, chunk_hash=chunk_hash)
        chunk_path = cache.joinpath(results_file_name)

        if not chunk_path.exists():
            chunk_path.parent.mkdir(parents=True, exist_ok=True)

            if chunk['key'].endswith('.zst'):
                data = xr.load_dataset(s3tethys.decompress_stream_to_object(io.BytesIO(file_obj.read()), 'zstd'))
                H5(data).sel(exclude_coords=['station_geometry', 'chunk_date']).to_hdf5(chunk_path, compression='zstd')
                data.close()
                del data
            else:
                s3tethys.stream_to_file(file_obj, chunk_path)

        data_obj = chunk_path

    else:
        if return_raw:
            return file_obj

        if chunk['key'].endswith('.zst'):
            file_obj = s3tethys.decompress_stream_to_object(io.BytesIO(file_obj.read()), 'zstd')
            data = xr.load_dataset(file_obj.read(), engine='scipy')
        else:
            data = io.BytesIO(file_obj.read())

        h1 = H5(data)
        data_obj = io.BytesIO()
        h1 = result_filters(h1)
        h1.to_hdf5(data_obj, compression='zstd')

        if isinstance(data, xr.Dataset):
            data.close()
        del data
        del h1

    del file_obj

    return data_obj


def xr_concat(datasets: List[xr.Dataset]):
    """
    A much more efficient concat/combine of xarray datasets. It's also much safer on memory.
    """
    # Get variables for the creation of blank dataset
    coords_list = []
    chunk_dict = {}

    for chunk in datasets:
        coords_list.append(chunk.coords.to_dataset())
        for var in chunk.data_vars:
            if var not in chunk_dict:
                dims = tuple(chunk[var].dims)
                enc = chunk[var].encoding.copy()
                dtype = chunk[var].dtype
                _ = [enc.pop(d) for d in ['original_shape', 'source'] if d in enc]
                var_dict = {'dims': dims, 'enc': enc, 'dtype': dtype, 'attrs': chunk[var].attrs}
                chunk_dict[var] = var_dict

    try:
        xr3 = xr.combine_by_coords(coords_list, compat='override', data_vars='minimal', coords='all', combine_attrs='override')
    except:
        xr3 = xr.merge(coords_list, compat='override', combine_attrs='override')

    # Run checks - requires psutil which I don't want to make it a dep yet...
    # available_memory = getattr(psutil.virtual_memory(), 'available')
    # dims_dict = dict(xr3.coords.dims)
    # size = 0
    # for var, var_dict in chunk_dict.items():
    #     dims = var_dict['dims']
    #     dtype_size = var_dict['dtype'].itemsize
    #     n_dims = np.prod([dims_dict[dim] for dim in dims])
    #     size = size + (n_dims*dtype_size)

    # if size >= available_memory:
    #     raise MemoryError('Trying to create a dataset of size {}MB, while there is only {}MB available.'.format(int(size*10**-6), int(available_memory*10**-6)))

    # Create the blank dataset
    for var, var_dict in chunk_dict.items():
        dims = var_dict['dims']
        shape = tuple(xr3[c].shape[0] for c in dims)
        xr3[var] = (dims, np.full(shape, np.nan, var_dict['dtype']))
        xr3[var].attrs = var_dict['attrs']
        xr3[var].encoding = var_dict['enc']

    # Update the attributes in the coords from the first ds
    for coord in xr3.coords:
        xr3[coord].encoding = datasets[0][coord].encoding
        xr3[coord].attrs = datasets[0][coord].attrs

    # Fill the dataset with data
    for chunk in datasets:
        for var in chunk.data_vars:
            if isinstance(chunk[var].variable._data, np.ndarray):
                xr3[var].loc[chunk[var].transpose(*chunk_dict[var]['dims']).coords.indexes] = chunk[var].transpose(*chunk_dict[var]['dims']).values
            elif isinstance(chunk[var].variable._data, xr.core.indexing.MemoryCachedArray):
                c1 = chunk[var].copy().load().transpose(*chunk_dict[var]['dims'])
                xr3[var].loc[c1.coords.indexes] = c1.values
                c1.close()
                del c1
            else:
                raise TypeError('Dataset data should be either an ndarray or a MemoryCachedArray.')

    return xr3


def filter_mod_dates(results, from_mod_date=None, to_mod_date=None):
    """
    Need to do this because xarray "where" is useless...
    """
    if ((from_mod_date is not None) or (to_mod_date is not None)) and ('modified_date' in results):
        mod_dates = results['modified_date'].copy().load()

        if (from_mod_date is not None) and (to_mod_date is not None):
            mod_bool = (mod_dates >= pd.Timestamp(from_mod_date)) & (mod_dates <= pd.Timestamp(to_mod_date))
        elif (from_mod_date is not None):
            mod_bool = (mod_dates >= pd.Timestamp(from_mod_date))
        elif (to_mod_date is not None):
            mod_bool = (mod_dates <= pd.Timestamp(to_mod_date))

        data_vars1 = [var for var in results.data_vars if 'time' in results[var].dims]

        results[data_vars1] = results[data_vars1].where(mod_bool)

        return results.dropna('time', how='all')
    else:
        return results


def results_concat(results_list, output_path=None, from_date=None, to_date=None, from_mod_date=None, to_mod_date=None, compression='lzf'):
    """

    """
    if output_path is None:
        output_path = io.BytesIO()
        compression = 'zstd'

    h1 = H5(results_list)
    h1 = result_filters(h1, from_date, to_date)
    h1.to_hdf5(output_path, compression=compression)

    xr3 = xr.open_dataset(output_path, engine='h5netcdf', cache=False)

    ## Deal with mod dates filters
    if ((from_mod_date is not None) or (to_mod_date is not None)) and ('modified_date' in xr3):
        xr3 = filter_mod_dates(xr3, from_mod_date, to_mod_date)

    return xr3







































