import requests

api_url = "http://85.193.80.133:8080"
api_key = 'key1-admin'
payload = {
    "command": "STATUS",
    "hubId": "hub123",
}
headers = {
    "Content-Type": "application/json",
    "Authorization": "key1-admin",
}

response = requests.post(api_url, json=payload, headers=headers)

print(response.status_code)
print(response.json())