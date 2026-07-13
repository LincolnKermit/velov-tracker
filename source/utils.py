import json, os, requests, dotenv

# Load .env for local runs; in CI the key is provided as an environment variable.
dotenv.load_dotenv()
jcd_api_key = os.getenv("JCD_API_KEY")
contract = "lyon"

def get_stations():
    if not jcd_api_key:
        raise RuntimeError("JCD_API_KEY is not set (add it to .env locally or as a GitHub secret).")
    headers = {
        "Accept": "application/json"
    }
    url = f"https://api.jcdecaux.com/vls/v3/stations?contract={contract}&apiKey={jcd_api_key}"
    try:
        response = requests.get(url, headers=headers)
    except requests.exceptions.ConnectionError:
        print("Connection error : Check your network connection and try again.")
        raise
    print("API response status code:", response.status_code)
    response.raise_for_status()
    return response.json()
