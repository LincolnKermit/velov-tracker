import json, requests, dotenv

dotenv.load_dotenv()
jcd_api_key = dotenv.get_key(".env", "JCD_API_KEY")
contract = "lyon"

print(jcd_api_key)

def get_stations():
    headers = {
        "Accept": "application/json"
    }
    url = f"https://api.jcdecaux.com/vls/v3/stations?contract={contract}&apiKey={jcd_api_key}"
    response = requests.get(url, headers=headers)
    return json.loads(response.text)