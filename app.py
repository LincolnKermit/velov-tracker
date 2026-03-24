import folium
from utils import get_stations
point_location = ["52.193312","3.12122"]
# place the point



tiles = 'VeloV Stations'
map = folium.Map(location=(45.750000, 4.850000), zoom_start=13)#location - the center of the map, zoom_start - the resolution



#functions


# 'totalStands': {'availabilities': {'bikes': 1, 'stands': 27, 'mechanicalBikes': 1, 'electricalBikes': 0, 'electricalInternalBatteryBikes': 0, 'electricalRemovableBatteryBikes': 0}, 'capacity': 30}, 'mainStands': {'availabilities': {'bikes': 1, 'stands': 27, 'mechanicalBikes': 1, 'electricalBikes': 0, 'electricalInternalBatteryBikes': 0, 'electricalRemovableBatteryBikes': 0}, 'capacity': 30}, 'overflowStands': None}

for station in get_stations():
    print("------------------------------")
    print(station["number"])
    print(station["name"])
    print(station["address"])
    print(station["position"])
    print(station["totalStands"]["availabilities"]["bikes"])
    print("------------------------------")
    print("\n")
    location = [station["position"]["latitude"], station["position"]["longitude"]]
    texte = ("Station " + station["name"], "Vélov dispo : " + str(station["totalStands"]["availabilities"]["bikes"]))
    if station["totalStands"]["availabilities"]["bikes"] == 0:
        status_color = "red"
    elif station["totalStands"]["availabilities"]["bikes"] < 5 and station["totalStands"]["availabilities"]["bikes"] > 0:
        status_color = "orange"
    elif station["totalStands"]["availabilities"]["bikes"] >= 5 and station["totalStands"]["availabilities"]["bikes"] < 10:
        status_color = "yellow"
    elif station["totalStands"]["availabilities"]["bikes"] >= 10:
        status_color = "green"
    elif station["totalStands"]["availabilities"]["bikes"] == None:
        status_color = "gray"
    marqueur = folium.Marker(location = location, popup = texte, icon=folium.Icon(color=f"{status_color}"))
    marqueur.add_to(map)
map.save("map.html")