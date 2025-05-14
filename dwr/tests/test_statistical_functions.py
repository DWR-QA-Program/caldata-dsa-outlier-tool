import numpy as np
import pandas as pd
import pytest

from scipy import stats
from outlier_tool import od

@pytest.fixture
def sample_submersible_sensor_data():
    time = pd.date_range(start='2025-01-01', periods=10, freq='D')
    data = np.random.uniform(6.5, 8.5, size=10)
    sample_data = pd.Series(data, index=time)
    return sample_data

def test_z_score(sample_submersible_sensor_data):
    output_ts = od.z_score_test(sample_submersible_sensor_data)
    assert len(output_ts) == len(sample_submersible_sensor_data)
