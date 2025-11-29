import requests

url = "https://fantasy.premierleague.com/api/bootstrap-static/"
data = requests.get(url).json()
print(data["teams"][0].keys())
print(data["teams"][0]["short_name"])
