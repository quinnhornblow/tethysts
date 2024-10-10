"""
Created on 2021-04-27.

@author: Mike K
"""


import pytest
import requests
from tethysts import Tethys
from tethysts.utils import public_remote_key, read_json_zstd


# %% tmp for ecan
@pytest.fixture()
def t1():
    with requests.get(public_remote_key) as resp:
        resp.raise_for_status()
        remotes = read_json_zstd(resp.content)
    remotes = [remotes[2]]  # ecan
    return Tethys(remotes=remotes)


@pytest.fixture()
def dataset_id():
    return "c3a09c8a5da175897916e8e8"


@pytest.fixture()
def station_ids():
    return ["d3680a5334d01edf08702d4d"]


def test_get_results(t1, dataset_id, station_ids):
    s1 = t1.get_results(dataset_id=dataset_id, station_ids=station_ids)

    assert len(s1) > 0
