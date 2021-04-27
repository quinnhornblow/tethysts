"""
Created on 2020-11-05.

@author: Mike K
"""
import os
import numpy as np
import xarray as xr
import pandas as pd
import orjson
# import yaml
from datetime import datetime
import copy
from multiprocessing.pool import ThreadPool
# import shapely
from tethysts.utils import get_object_s3, result_filters, process_results_output, read_json_zstd, key_patterns

pd.options.display.max_columns = 10


##############################################
### Parameters



##############################################
### Class


class Tethys(object):
    """
    The base Tethys object.

    Parameters
    ----------
    remotes_list : list of dict
        list of dict of the S3 remotes to access. The dicts must contain:
        bucket and connection_config.

        bucket : str
            A string of the bucket name.
        connection_config : dict or str
            A dict of strings of service_name, s3, endpoint_url, aws_access_key_id, and aws_secret_access_key. Or it could be a string of the public_url endpoint.

    Returns
    -------
    tethys object
    """

    ## Initial import and assignment function
    def __init__(self, remotes_list=None):
        """

        """
        setattr(self, 'datasets', [])
        setattr(self, '_datasets', {})
        setattr(self, '_remotes', {})
        setattr(self, '_stations', {})
        setattr(self, '_key_patterns', key_patterns)

        if isinstance(remotes_list, list):
            datasets = self.get_datasets(remotes_list)

        else:
            pass


    def get_datasets(self, remotes_list, threads=30):
        """
        The function to get datasets from many remotes.

        Parameters
        ----------
        remotes_list : list of dict
            list of dict of the S3 remotes to access. The dicts must contain:
            bucket and connection_config.
            bucket : str
                A string of the bucket name.
            connection_config : dict or str
                A dict of strings of service_name, s3, endpoint_url, aws_access_key_id, and aws_secret_access_key. Or it could be a string of the public_url endpoint.
        threads : int
            The number of threads to use. I.e. the number of simultaneous remote reads.

        Returns
        -------
        dict
            of datasets
        """
        output = ThreadPool(threads).map(self.get_remote_datasets, remotes_list)

        return self.datasets


    def get_remote_datasets(self, remote):
        """
        Get datasets from an individual remote. Saves result into the object.

        Parameters
        ----------
        remote : dict
            dict of the S3 remote to access. The dict must contain:
            bucket and connection_config.
            bucket : str
                A string of the bucket name.
            connection_config : dict or str
                A dict of strings of service_name, s3, endpoint_url, aws_access_key_id, and aws_secret_access_key. Or it could be a string of the public_url endpoint.

        Returns
        -------
        None
        """
        try:
            ds_obj = get_object_s3(self._key_patterns['datasets'], remote['connection_config'], remote['bucket'])
            ds_list = read_json_zstd(ds_obj)

            ds_list2 = copy.deepcopy(ds_list)
            # [l.pop('properties') for l in ds_list2]
            self.datasets.extend(ds_list2)

            ds_dict = {d['dataset_id']: d for d in ds_list}
            remote_dict = {d: {'dataset_id': d, 'bucket': remote['bucket'], 'connection_config': remote['connection_config']} for d in ds_dict}

            self._datasets.update(ds_dict)
            self._remotes.update(remote_dict)

        except:
            print('No datasets.json.zst file in S3 bucket')


    def get_stations(self, dataset_id, results_object_keys=False):
        """
        Method to return the stations associated with a dataset.

        Parameters
        ----------
        dataset_id : str
            The dataset_id of the dataset.
        results_object_keys : bool
            Shoud the results object keys be returned? The results object keys list the available results in Tethys.

        Returns
        -------
        list of dict
            of station data
        """
        remote = self._remotes[dataset_id]

        site_key = self._key_patterns['stations'].format(dataset_id=dataset_id)

        try:
            stn_obj = get_object_s3(site_key, remote['connection_config'], remote['bucket'])
            stn_list = read_json_zstd(stn_obj)
            stn_list = [s for s in stn_list if isinstance(s, dict)]

            self._stations.update({dataset_id: {s['station_id']: s for s in copy.deepcopy(stn_list)}})

            # TODO: Run spatial query here!

            if not results_object_keys:
                s = [s.pop('results_object_key') for s in stn_list]

            return stn_list

        except:
            print('No stations.json.zst file in S3 bucket')


    def get_run_dates(self, dataset_id, station_id):
        """
        Function to get the run dates of a particular dataset and station.

        Parameters
        ----------
        dataset_id : str
            The dataset_id of the dataset.
        station_id : str
            The station_id of the associated station.

        Returns
        -------
        list
        """
        if dataset_id not in self._stations:
            stns = self.get_stations(dataset_id)

        dataset_stn = self._stations[dataset_id][station_id]

        run_dates = np.unique([ob['run_date'].split('+')[0] if '+' in ob['run_date'] else ob['run_date'] for ob in dataset_stn['results_object_key']]).tolist()

        return run_dates


    def _get_results_obj_key_s3(self, dataset_id, station_id, run_date):
        """

        """
        if dataset_id not in self._stations:
            stns = self.get_stations(dataset_id)

        dataset_stn = self._stations[dataset_id][station_id]

        obj_keys = dataset_stn['results_object_key']
        obj_keys_df = pd.DataFrame(obj_keys)
        obj_keys_df['run_date'] = pd.to_datetime(obj_keys_df['run_date']).dt.tz_localize(None)
        last_run_date = obj_keys_df['run_date'].max()
        last_key = obj_keys_df[obj_keys_df['run_date'] == last_run_date]['key']

        ## Set the correct run_date
        if isinstance(run_date, (str, pd.Timestamp)):
            run_date1 = pd.Timestamp(run_date)

            obj_key_df = obj_keys_df[obj_keys_df['run_date'] == run_date1]

            if obj_key_df.empty:
                print('Requested run_date is not available, returning last run_date results')
                obj_key = last_key
            else:
                obj_key = obj_key_df['key']
        else:
            obj_key = last_key

        return obj_key


    def get_results(self, dataset_id, station_id, from_date=None, to_date=None, from_mod_date=None, to_mod_date=None, modified_date=False, quality_code=False, run_date=None, remove_height=False, output='DataArray'):
        """
        Function to query the time series data given a specific dataset_id and station_id. Multiple optional outputs.

        Parameters
        ----------
        dataset_id : str
            The dataset_id of the dataset.
        station_id : str
            The station_id of the associated station.
        from_date : str, Timestamp, datetime, or None
            The start date of the selection.
        to_date : str, Timestamp, datetime, or None
            The end date of the selection.
        from_mod_date : str, Timestamp, datetime, or None
            Only return data post the defined modified date.
        to_mod_date : str, Timestamp, datetime, or None
            Only return data prior to the defined modified date.
        modified_date : bool
            Should the modified dates be returned if they exist?
        quality_code : bool
            Should the quality codes be returned if they exist?
        run_date : str or Timestamp
            The run_date of the results to be returned. Defaults to None which will return the last run date.
        remove_height : bool
            Should the height dimension be removed from the output?
        output : str
            Output format of the results. Options are:
                Dataset - return the entire contents of the netcdf file as an xarray Dataset,
                DataArray - return the requested dataset parameter as an xarray DataArray,
                Dict - return a dictionary of results from the DataArray,
                json - return a json str of the Dict.

        Returns
        -------
        Whatever the output was set to.
        """

        ## Get parameters
        dataset = self._datasets[dataset_id]
        parameter = dataset['parameter']
        remote = self._remotes[dataset_id]

        ## Get object key
        obj_key = self._get_results_obj_key_s3(dataset_id, station_id, run_date)

        ## Get results
        ts_obj = get_object_s3(obj_key.iloc[0], remote['connection_config'], remote['bucket'], 'zstd')
        xr3 = xr.open_dataset(ts_obj)

        ## Filters
        ts_xr1 = result_filters(xr3, from_date, to_date, from_mod_date, to_mod_date, remove_height).expand_dims('station_id').set_coords('station_id')

        ## Output
        output1 = process_results_output(ts_xr1, parameter, modified_date, quality_code, output)

        return output1


    def get_bulk_results(self, dataset_id, station_ids, from_date=None, to_date=None, from_mod_date=None, to_mod_date=None, modified_date=False, quality_code=False, run_date=None, remove_height=False, output='DataArray', threads=30):
        """
        Function to bulk query the time series data given a specific dataset_id and a list of station_ids. The output will be specified by the output parameter and will be concatenated along the station_id dimension.

        Parameters
        ----------
        dataset_id : str
            The hashed str of the dataset_id.
        station_ids : list of str
            A list of hashed str of the site_ids.
        from_date : str, Timestamp, datetime, or None
            The start date of the selection.
        to_date : str, Timestamp, datetime, or None
            The end date of the selection.
        from_mod_date : str, Timestamp, datetime, or None
            Only return data post the defined modified date.
        to_mod_date : str, Timestamp, datetime, or None
            Only return data prior to the defined modified date.
        modified_date : bool
            Should the modified dates be returned if they exist?
        quality_code : bool
            Should the quality codes be returned if they exist?
        run_date : str or Timestamp
            The run_date of the results to be returned. Defaults to None which will return the last run date.
        remove_height : bool
            Should the height dimension be removed from the output?
        output : str
            Output format of the results. Options are:
                Dataset - return the entire contents of the netcdf file as an xarray Dataset,
                DataArray - return the requested dataset parameter as an xarray DataArray,
                Dict - return a dictionary of results from the DataArray,
                json - return a json str of the Dict.
        threads : int
            The number of simultaneous downloads.

        Returns
        -------
        Format specified by the output parameter
            Will be concatenated along the station_id dimension
        """
        dataset = self._datasets[dataset_id]
        parameter = dataset['parameter']

        lister = [(dataset_id, s, from_date, to_date, from_mod_date, to_mod_date, modified_date, quality_code, run_date, remove_height, 'Dataset') for s in station_ids]

        output1 = ThreadPool(threads).starmap(self.get_results, lister)
        output2 = [d if 'station_id' in list(d.coords) else d.expand_dims('station_id').set_coords('station_id') for d in output1]

        xr_ds1 = xr.concat(output2, 'station_id')

        ## Output
        output3 = process_results_output(xr_ds1, parameter, modified_date, quality_code, output)

        return output3



######################################
### Testing
