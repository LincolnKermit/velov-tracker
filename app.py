import folium, flask, os, webbrowser
from utils import get_stations

app = flask.Flask(__name__)

#functions

def setup():
    os.system("rm stations.txt")
    os.system("rm templates/map.html")


def load():
    tiles = 'VeloV Stations'
    map = folium.Map(location=(45.750000, 4.850000), zoom_start=13)#location - the center of the map, zoom_start - the resolution
    for station in get_stations():
        with open("stations.txt", "a") as f:
            f.write(str(station) + "\n")
            f.close()
        print("------------------------------")
        print("\n")
        location = [station["position"]["latitude"], station["position"]["longitude"]]
        available_bikes = int(station["totalStands"]["availabilities"]["bikes"])
        available_mechanical_bikes = int(station["totalStands"]["availabilities"]["mechanicalBikes"])
        available_electric_bikes = int(station["totalStands"]["availabilities"]["electricalBikes"])
        available_parking = int(station["totalStands"]["availabilities"]["stands"])
        available_capacity = int(station["totalStands"]["capacity"])
        texte = ("Station " + station["name"], "Vélov dispo : " + str(available_bikes))
        html_popup = f"""
        <h1> {station["name"]} </h1><br>
        <p>
        Vélov disponibles : {available_bikes}<br>
        Electriques : {available_electric_bikes}<br>
        Mécaniques : {available_mechanical_bikes}<br>
        <strong>Parking disponibles : {available_parking}/{available_capacity}</strong>
        </p>
        <p>
        {station["address"]}
        </p>
        <p>
        Status : {station["status"]}
        </p>
        <p>
        Dernière mise à jour : {station["lastUpdate"]}
        </p>
        """
        if available_bikes == 0:
            print("Station " + station["name"] + " has " + str(available_bikes) + " bikes available.")
            status_color = "red"
        elif available_bikes < 5 and available_bikes > 0:
            print("Station " + station["name"] + " has " + str(available_bikes) + " bikes available.")
            status_color = "orange"
        elif available_bikes >= 5:
            print("Station " + station["name"] + " has " + str(available_bikes) + " bikes available.")
            status_color = "green"
        elif available_bikes == None:
            print("Station " + station["name"] + " has no data available.")
            status_color = "gray"
        else:
            print("Station " + station["name"] + " has an unknown number of bikes available.")
            status_color = "blue"
        marqueur = folium.Marker(location = location, popup = html_popup, icon=folium.Icon(color=f"{status_color}"))
        marqueur.add_to(map)
    map.save("templates/map.html")


@app.route("/")
def index():
    return flask.render_template("map.html")


if __name__ == "__main__":
    setup()
    load()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False)