from outlier_tool import app as src

try:
    from datetime import datetime
    from pytz import timezone
    now_utc = datetime.now(timezone('UTC'))
    pacific_tz = timezone('US/Pacific')
    now_pacific = now_utc.astimezone(pacific_tz)
    print('Launched at: ' + now_pacific.strftime('%Y-%m-%d %H:%M:%S %Z%z'))
except Exception as e:
    print(f'Launched with exception: {e}')
app = src.app
