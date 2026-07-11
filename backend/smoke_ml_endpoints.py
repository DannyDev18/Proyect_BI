"""Smoke test end-to-end de los 6 casos de uso ML, ejecutado dentro del contenedor
backend (misma sesión DB + ModelLoader que usa la app real vía FastAPI)."""
import logging
logging.basicConfig(level=logging.INFO)

from app.database.session import SessionLocal
from app.ml.model_loader import ModelLoader
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.prediction_repository import PredictionRepository
from app.services.prediction_service import PredictionService

loader = ModelLoader(models_dir="/app/ml_models")
loader.load_all()

def new_service():
    """Sesión DB fresca por caso de uso -- imita la inyección de dependencias por
    request de FastAPI (get_db()), en vez de reutilizar una sola sesión para las 6
    llamadas (eso sí rompe: dataset_repository.py reusa self.db.connection() como
    context manager, que cierra la conexión subyacente tras el primer uso)."""
    db = SessionLocal()
    return PredictionService(PredictionRepository(db), DatasetRepository(db), loader), db

CLIENTE_ID = "100001"
PRODUCTO_COD = "2 608 690 573"
TRANSACCION_ID = "A0040030"
SUCURSAL = "SUC. EL REY"

print("\n=== 1. Ventas (forecast semana/mes) ===")
service, db = new_service()
r = service.get_sales_forecast(sucursal=None, granularidad="semana")
print("periodos_proyectados:", r["periodos_proyectados"])
print("metricas:", r["metricas"])
print("insights:", r["insights"])
assert r["periodos_proyectados"] > 0
assert r["metricas"].get("mae_modelo") is not None, "mae_modelo debe venir del sidecar real (H-09)"
assert r["metricas"].get("algoritmo"), "algoritmo debe venir del sidecar real (H-21-1)"
ultimo_pred = [d for d in r["historial_y_prediccion"] if d["monto_predicho"] is not None][-1]
print("ultimo monto_predicho (USD, debe ser miles, no ~12):", ultimo_pred["monto_predicho"])
assert ultimo_pred["monto_predicho"] > 100, "H-01: la predicción debe estar en escala USD real, no log1p"

print("\n=== 2. Demanda ===")
service, db = new_service()
d = service.get_demand_forecast(PRODUCTO_COD)
print("demanda predicha:", d)
db.close()

print("\n=== 3. Churn ===")
service, db = new_service()
c = service.get_churn_risk(CLIENTE_ID)
print("churn:", c)
db.close()

print("\n=== 4. Anomalias ===")
service, db = new_service()
a = service.get_anomaly_status(TRANSACCION_ID)
print("anomalia:", a)
assert a["score"] != 0.0 or a["es_anomalia"], "el score no debe quedar en el default 0.0 silencioso si hay features"
db.close()

print("\n=== 5. Recomendaciones ===")
service, db = new_service()
rec = service.get_product_recommendations(CLIENTE_ID)
print("recomendaciones:", rec)
db.close()

print("\n=== 6. Segmentacion RFM ===")
service, db = new_service()
seg = service.get_customer_segment(CLIENTE_ID)
print("segmento:", seg)
assert seg["nombre_segmento"] not in ("Error",), "no debe degradar a Error"
db.close()

print("\n=== TODOS LOS CASOS DE USO EJECUTARON SIN EXCEPCION ===")
