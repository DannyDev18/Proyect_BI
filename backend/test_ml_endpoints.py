import urllib.request
import urllib.parse
import urllib.error
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

users = [
    ("admin@empresa.com", "Admin123!"),
    ("gerente.norte@empresa.com", "Gerente123!"),
    ("bodega.uiodev@empresa.com", "Bodega123!"),
    ("ventas.uio01@empresa.com", "Ventas123!")
]

def get_token(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/auth/login", data=data)
    try:
        with urllib.request.urlopen(req) as res:
            resp_data = json.loads(res.read().decode())
            return resp_data["access_token"]
    except Exception as e:
        print(f"Failed to login {username}: {e}")
        return None

tokens = {}
for u, p in users:
    tokens[u] = get_token(u, p)
    
print("--- TEST MODEL INFERENCE ENDPOINTS ---")

def fetch(url, token):
    if not token: return
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as res:
            print("OK 200", res.read().decode()[:200])
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}", e.read().decode())

t_g = tokens.get("gerente.norte@empresa.com")
print("GERENCIA (Sales Predict):")
fetch(f"{BASE_URL}/analytics/gerencia/sales-prediction", t_g)

t_b = tokens.get("bodega.uiodev@empresa.com")
print("BODEGA (Demand Predict):")
fetch(f"{BASE_URL}/analytics/bodega/demand-forecasting?producto_cod=030", t_b)

t_v = tokens.get("ventas.uio01@empresa.com")
print("VENTAS (Churn Predict):")
fetch(f"{BASE_URL}/analytics/ventas/churn-risk?cliente_id=C001", t_v)

t_a = tokens.get("admin@empresa.com")
print("ADMIN (Anomaly Detect):")
fetch(f"{BASE_URL}/analytics/admin/anomalies?transaccion_id=T001", t_a)
