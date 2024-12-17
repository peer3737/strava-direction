import logging
import os
from database.db import Connection
import uuid
from supporting import aws
import math


class CorrelationIdFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        # Generate a new correlation ID
        self.correlation_id = str(uuid.uuid4())

    def filter(self, record):
        # Add correlation ID to the log record
        record.correlation_id = self.correlation_id
        return True


# Logging formatter that includes the correlation ID
formatter = logging.Formatter('[%(levelname)s] [%(asctime)s] [Correlation ID: %(correlation_id)s] %(message)s')

# Set up the root logger
log = logging.getLogger()
log.setLevel("INFO")
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

# Remove existing handlers
for handler in log.handlers:
    log.removeHandler(handler)

# Add a new handler with the custom formatter
handler = logging.StreamHandler()
handler.setFormatter(formatter)
log.addHandler(handler)

# Add the CorrelationIdFilter to the logger
correlation_filter = CorrelationIdFilter()
log.addFilter(correlation_filter)
weather_table = os.getenv('WEATHER_TABLE')

def calculate_bearing(lat1, lon1, lat2, lon2, wind_direction):
    colors = {
        "0": "FF0000",
        "5": "FF1100",
        "10": "FF2200",
        "15": "FF3300",
        "20": "FF4400",
        "25": "FF5500",
        "30": "FF6600",
        "35": "FF7700",
        "40": "FF8800",
        "45": "FF8800",
        "50": "FF9800",
        "55": "FFA800",
        "60": "FFB800",
        "65": "FFC800",
        "70": "FFD800",
        "75": "FFE800",
        "80": "FFF000",
        "85": "FFFF00",
        "90": "FFFF00",
        "95": "EFFF00",
        "100": "DFFF00",
        "105": "CFFF00",
        "110": "BFFF00",
        "115": "AFFF00",
        "120": "9FFF00",
        "125": "8FFF00",
        "130": "88FF00",
        "135": "88FF00",
        "140": "78FF00",
        "145": "68FF00",
        "150": "58FF00",
        "155": "48FF00",
        "160": "38FF00",
        "165": "28FF00",
        "170": "18FF00",
        "175": "08FF00",
        "180": "00FF00"
    }
    # Convert latitude and longitude from degrees to radians
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    # Calculate the differences
    d_lon = lon2 - lon1

    # Calculate bearing
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))

    initial_bearing = math.atan2(x, y)

    # Convert bearing from radians to degrees and normalize to 0-360°
    initial_bearing = math.degrees(initial_bearing)
    bearing = (initial_bearing + 360) % 360

    direction = abs(wind_direction - bearing)
    if direction > 180:
        direction = 360 - direction

    closest_color = str(min(colors, key=lambda dt: abs(float(dt) - direction)))

    # print(f"Running direction = {bearing}, Wind direction = {wind_direction}, color = {closest_color}")
    return colors[str(closest_color)]

def lambda_handler(event, context):
    activity_id = event.get("activity_id")
    log.info(f"Start handling laps for activity {activity_id}")
    database_id = os.getenv('DATABASE_ID')
    database_settings = aws.dynamodb_query(table='database_settings', id=database_id)
    db_host = database_settings[0]['host']
    db_user = database_settings[0]['user']
    db_password = database_settings[0]['password']
    db_port = database_settings[0]['port']
    db = Connection(user=db_user, password=db_password, host=db_host, port=db_port, charset="utf8mb4")

    activities = db.get_specific(table='activity', where=f'id = {activity_id}', order_by_type='desc')
    total_act = len(activities)
    act_counter = 0
    for activity in activities:
        activity_id = activity[0]
        act_counter += 1
        log.info(f'Handling activity {activity_id} ({act_counter}/{total_act})')
        stream = db.get_specific(table="activity_streams", where=f"activity_id = {activity_id}")
        weather = db.get_specific(table=weather_table, where=f"activity_id = {activity_id}")
        wind = weather[0][4].split(', ')

        activity_latlngs = stream[0][5].split('],[')
        activity_latlngs[0] = activity_latlngs[0][1:]
        activity_latlngs[len(activity_latlngs) - 1] = activity_latlngs[len(activity_latlngs) - 1][:-1]
        color_values = ["FF0000"]
        for i in range(0, len(activity_latlngs) - 2):
            wind_direction = float(wind[i])
            lat1 = float(activity_latlngs[i].split(',')[0].strip())
            lon1 = float(activity_latlngs[i].split(',')[1].strip())
            lat2 = float(activity_latlngs[(i + 1)].split(',')[0].strip())
            lon2 = float(activity_latlngs[(i + 1)].split(',')[1].strip())
            color = calculate_bearing(lat1, lon1, lat2, lon2, wind_direction)
            color_values.append(color)

        json_data = {
            "activity_id": activity_id,
            "colors": ', '.join(color_values)
        }
        db.insert(table="running_colors", json_data=json_data)

