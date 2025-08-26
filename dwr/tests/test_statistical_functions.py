import numpy as np
import pandas as pd
import pytest
from outlier_tool import od_core as od


@pytest.fixture
def sample_submersible_sensor_data():
    np.random.seed(seed=42)
    time = pd.date_range(start='2025-01-01', periods=100, freq='D')
    data = np.abs(np.random.randn(100) * 5)
    sample_data = pd.Series(data, index=time)
    sample_data = sample_data.drop(index=pd.Timestamp('2025-01-23 00:00:00'))
    sample_data[40:42] = np.nan
    sample_data[44:47] = 7.0
    return sample_data


def test_time_gap(sample_submersible_sensor_data):
    output_ts = od.time_gap_test(ts=pd.Series(sample_submersible_sensor_data.index), number=1, unit='days')
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 1
    with pytest.raises(ValueError, match='No input data.'):
        od.time_gap_test(ts=pd.Series([]), number=1, unit='days')


def test_value_gap(sample_submersible_sensor_data):
    output_ts = od.value_gap_test(ts=sample_submersible_sensor_data)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 2
    with pytest.raises(ValueError, match='No input data.'):
        od.value_gap_test(ts=pd.Series([]))


def test_gross_range(sample_submersible_sensor_data):
    output_ts = od.gross_range_test(ts=sample_submersible_sensor_data, minimum=4, maximum=8)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 64
    with pytest.raises(ValueError, match='No input data.'):
        od.gross_range_test(ts=pd.Series([]), minimum=4, maximum=8)


def test_flat_line(sample_submersible_sensor_data):
    output_ts = od.flat_line_test(ts=sample_submersible_sensor_data, number_of_repeated_values=3)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 3
    with pytest.raises(ValueError, match='No input data.'):
        od.flat_line_test(ts=pd.Series([]), number_of_repeated_values=3)


def test_z_score(sample_submersible_sensor_data):
    output_ts = od.z_score_test(ts=sample_submersible_sensor_data, number_of_standard_deviations=1)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 33
    with pytest.raises(ValueError, match='No input data.'):
        od.z_score_test(ts=pd.Series([]))


def test_modified_z_score(sample_submersible_sensor_data):
    output_ts = od.modified_z_score_test(ts=sample_submersible_sensor_data, median_absolute_deviation=2)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 7
    with pytest.raises(ValueError, match='No input data.'):
        od.modified_z_score_test(ts=pd.Series([]))


def test_tukey_iqr(sample_submersible_sensor_data):
    output_ts = od.tukey_iqr_test(ts=sample_submersible_sensor_data)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 1
    with pytest.raises(ValueError, match='No input data.'):
        od.tukey_iqr_test(ts=pd.Series([]))


def test_spike(sample_submersible_sensor_data):
    output_ts = od.spike_detection_test(ts=sample_submersible_sensor_data)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 44
    with pytest.raises(ValueError, match='No input data.'):
        od.spike_detection_test(ts=pd.Series([]))


def test_rate_of_change(sample_submersible_sensor_data):
    output_ts = od.rate_of_change_test(ts=sample_submersible_sensor_data, threshold_value=1.1)
    assert len(output_ts) == len(sample_submersible_sensor_data)
    assert np.count_nonzero(output_ts) == 59
    with pytest.raises(ValueError, match='No input data.'):
        od.rate_of_change_test(ts=pd.Series([]), threshold_value=1.1)
