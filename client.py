import requests
from datetime import datetime, timedelta
import pytz

# ----------------------------
# CONFIG
# ----------------------------
ambient_url = "https://api.ambientweather.net/v1/devices?applicationKey=40b33f6a63754b5fb70a4d5fe557c64efcdd693597924c21986b47e71e1e68eb&apiKey=c5cc20bfdc0446aaaddd4543eb04c64c4852dcd72d1f4d5d8c7f207c1d21036a"
weathercom_url = "https://api.weather.com/v2/pws/observations/all/1day?stationId=KFLMILTO379&format=json&units=e&apiKey=8de2d8b3a93542c9a2d8b3a935a2c909"
nws_url = "https://api.weather.gov/stations/KNDZ/observations/latest"
clientraw_file = "clientraw.txt"
tz = pytz.timezone("America/Chicago")

# ----------------------------
# UTILS
# ----------------------------
def f_to_c(f):
    return round((f - 32) * 5 / 9, 1) if f is not None else -100

def mph_to_kts(mph):
    return round(mph * 0.868976, 1) if mph is not None else -100

def inch_to_mm(inches):
    return round(inches * 25.4, 1) if inches is not None else 0

def hpa_to_inhg(hpa):
    return round(hpa * 0.02953, 2) if hpa != -100 else -100

def safe_get(d, *keys, default=-100):
    for key in keys:
        if d is None or key not in d:
            return default
        d = d[key]
    return d if d is not None else default

# ----------------------------
# FETCH AMBIENT WEATHER
# ----------------------------
resp_aw = requests.get(ambient_url).json()
if not resp_aw or "lastData" not in resp_aw[0]:
    raise Exception("Ambient Weather API returned empty or invalid data.")

aw = resp_aw[0]['lastData']
station_name_raw = resp_aw[0]['info']['name']

temp_out = f_to_c(aw.get('tempf', -100))
humidity_out = aw.get('humidity', -100)
windspeed = mph_to_kts(aw.get('windspeedmph', -100))
windgust = mph_to_kts(aw.get('windgustmph', -100))
winddir = aw.get('winddir', -100)
baro_hpa = round(aw.get('baromabsin', -100) * 33.8639, 1) if aw.get('baromabsin') is not None else -100
rain_day = inch_to_mm(aw.get('dailyrainin', 0))
rain_month = inch_to_mm(aw.get('monthlyrainin', 0))
rain_year = inch_to_mm(aw.get('yearlyrainin', 0))
dewpoint = f_to_c(aw.get('dewPoint', -100))
lightning_day = aw.get('lightning_day', 0)
lightning_time = aw.get('lightning_time', 0)
lightning_distance = aw.get('lightning_distance', 0)

# ----------------------------
# FETCH WEATHER.COM
# ----------------------------
resp_w = requests.get(weathercom_url).json()
obs_w = resp_w.get('observations', [])

now_local = datetime.now(tz)
one_hour_ago = now_local - timedelta(hours=1)

last_hour_speeds = []
last_hour_dirs = []
last_hour_temp = []
last_hour_rain = []

for obs in reversed(obs_w):
    obs_time_str = obs.get('obsTimeLocal')
    if obs_time_str:
        obs_time = tz.localize(datetime.strptime(obs_time_str, "%Y-%m-%d %H:%M:%S"))
        if one_hour_ago <= obs_time <= now_local:
            last_hour_speeds.append(mph_to_kts(safe_get(obs, 'imperial', 'windspeedAvg', default=0)))
            last_hour_dirs.append(safe_get(obs, 'winddirAvg', default=0))
            last_hour_temp.append(f_to_c(safe_get(obs, 'imperial', 'temp', default=0)))
            last_hour_rain.append(inch_to_mm(safe_get(obs, 'imperial', 'precipRate', default=0)))

# Pad arrays to length 10
for arr in [last_hour_speeds, last_hour_dirs, last_hour_temp, last_hour_rain]:
    while len(arr) < 10:
        arr.insert(0, 0)

# Max/min temps
if obs_w:
    max_temp = max(f_to_c(safe_get(obs, 'imperial', 'tempHigh', default=-100)) for obs in obs_w)
    min_temp = min(f_to_c(safe_get(obs, 'imperial', 'tempLow', default=-100)) for obs in obs_w)
    max_gust_today = max(mph_to_kts(safe_get(obs, 'imperial', 'windgustHigh', default=-100)) for obs in obs_w)
else:
    max_temp = min_temp = max_gust_today = -100

# Max hourly precip rate (mm) for fields 37 & 38
max_precip_in = max(
    safe_get(obs, 'imperial', 'precipRate', default=0)
    for obs in obs_w
) if obs_w else 0
max_precip_mm = inch_to_mm(max_precip_in)

# Average wind direction
avg_wind_dir = round(sum([d for d in last_hour_dirs if d > 0]) / len([d for d in last_hour_dirs if d > 0])) if any(last_hour_dirs) else winddir

# ----------------------------
# FETCH NWS DATA
# ----------------------------
resp_nws = requests.get(nws_url).json()
nws = resp_nws.get('properties', {})

condition_text = safe_get(nws, 'textDescription', default='Unknown')
cloud_base = safe_get(nws, 'cloudLayers', 0, 'base', default=-100) if nws.get('cloudLayers') else -100

# ----------------------------
# BUILD CLIENTRAW LINE
# ----------------------------
fields = []

# 0–6
fields.append(12345)               # ID code
fields.append(round(windspeed, 1)) # Avg wind
fields.append(round(windspeed, 1)) # Current wind
fields.append(winddir)              # Wind direction
fields.append(round(temp_out, 1))   # Temperature
fields.append(humidity_out)         # Humidity
fields.append(baro_hpa)

# 7–9: rain
fields.append(rain_day)
fields.append(rain_month)
fields.append(rain_year)

# 10–31: placeholders
while len(fields) < 32:
    fields.append(-100)

# 32: station + timestamp
fields.append(f"{station_name_raw.lower().replace(' ', '')},fl-{now_local.strftime('%I:%M:%S_%p')}")

# 33–45: placeholders and lightning info
fields.extend([-100]*3)
fields.append(lightning_day)
fields.extend([-100]*8)

# 46–55: last hour wind speeds
fields.extend(last_hour_speeds)

# 56–65: last hour wind directions
fields.extend(last_hour_dirs)

# 66–67: max hourly precip rate mm (fields 37 & 38)
fields.append(max_precip_mm)
fields.append(max_precip_mm)

# Max gust today, dewpoint, cloud base
fields.append(max_gust_today)
fields.append(dewpoint)
fields.append(cloud_base)

# Fill remaining positions to 180
while len(fields) < 180:
    fields.append(-100)

# ----------------------------
# WRITE FILE
# ----------------------------
with open(clientraw_file, "w") as f:
    f.write(" ".join(str(f) for f in fields))

print(f"clientraw.txt updated at {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
