import folium, flask, os, webbrowser, json
from utils import get_stations
from ux import filter_html

app = flask.Flask(__name__)

def setup():
    os.system("rm stations.txt")
    os.system("rm templates/map.html")

def load():
    map = folium.Map(location=(45.750000, 4.850000), zoom_start=13)
    stations_data = {}  # { marker_id: {e, m, s, b} } e lectrical, m echanical, s tands, b ikes

    for i, station in enumerate(get_stations()):
        with open("stations.txt", "a") as f:
            f.write(str(station) + "\n")
        name                 = station["name"]
        location             = [station["position"]["latitude"], station["position"]["longitude"]]
        available_bikes      = int(station["totalStands"]["availabilities"]["bikes"])
        available_electrical = int(station["totalStands"]["availabilities"]["electricalBikes"])
        available_mechanical = int(station["totalStands"]["availabilities"]["mechanicalBikes"])
        available_stands     = int(station["totalStands"]["availabilities"]["stands"])
        available_capacity   = int(station["totalStands"]["capacity"])

        html_popup = f"""
        <div>
        <h1> {name} </h1><br>
        <p>
        Vélov disponibles : {available_bikes}<br>
        Electriques : {available_electrical}<br>
        Mécaniques : {available_mechanical}<br>
        <strong>Parking disponibles : {available_stands}/{available_capacity}</strong>
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
        </div>
        """

        if available_bikes == 0:
            status_color = "red"
        elif 0 < available_bikes < 5:
            status_color = "orange"
        elif available_bikes >= 5:
            status_color = "green"
        else:
            status_color = "gray"

        marqueur = folium.Marker(
            location = location,
            popup    = html_popup,
            icon     = folium.Icon(color=status_color)
        )
        marqueur.add_to(map)

        # Stocke les données indexées par position dans le même ordre que Leaflet
        stations_data[i] = {
            "e": available_electrical,
            "m": available_mechanical,
            "s": available_stands,
            "b": available_bikes,
        }

    # Injecte les données comme variable JS globale
    data_script = f"<script>var STATIONS_DATA = {json.dumps(stations_data)};</script>"
    map.get_root().html.add_child(folium.Element(data_script))
    map.get_root().html.add_child(folium.Element(filter_html))
    map.get_root().header.add_child(folium.Element('<link rel="stylesheet" href="/static/style.css">'))
    map.save("templates/map.html")

@app.route("/")
def index():
    return flask.render_template("map.html")

if __name__ == "__main__":
    setup()
    load()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False)