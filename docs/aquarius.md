# Integrating with the Aquarius API

The tool was not designed to directly integrate with any single database. However, as
numerous teams are in the process of procuring Aquarius, it seemed prudent to put
together brief documentation of how the tool could interface with it in the future.

Aquarius stores data in an AWS RDS database; this data is exposed via a REST API.
The API allows user to pull (GET) or publish (POST) data.
Some API references:
- [Acquisition API](https://aq-demo.aquaticinformatics.net/AQUARIUS/Acquisition/v2/swagger-ui/)
- [Provisioning API](https://aq-demo.aquaticinformatics.net/AQUARIUS/provisioning/v1/swagger-ui/)
- [Publishing API](https://aq-demo.aquaticinformatics.net/AQUARIUS/Publish/v2/swagger-ui/)

Based on Aquarius' documentation, the following endpoints appear to be good starting points:

- Reading Data: `GET /AQUARIUS/Publish/v2/GetTimeSeriesData`
   -  Use this to retrieve time series data. You can specify the series by its unique ID and
      filter by a date range.
- Writing Data: `POST /AQUARIUS/Acquisition/v2/timeseries/append`
    - This endpoint allows you to append new data points to an existing time series.

# API usage considerations

- For optimal performance, avoid using the API to transfer large amounts of data at once.
- The `overwriteappend` API may be more preferable than the simple `append` one. It would
certainly be possible to simply `append` to a table within Aquarius designated for flagged
data. But, it may be the case that the tool will instead need to update existing records
with outlier metadata.


# Code example

Below is a basic, untested idea of what an API call could look like.

```python
import requests

base_url = 'TBD'

# Prepare the data and request
url = f"https://{base_url}/AQUARIUS/Acquisition/v2/timeseries/append"
headers = {'Content-Type': 'application/json'}
payload = {
    "TimeSeriesUniqueId": "your_timeseries_unique_id",
    "Points": [{"Timestamp": "2025-09-22T12:00:00Z", "Value": 15.1}]
}

# Post the new data
response = requests.post(url, headers=headers, json=payload)
```
