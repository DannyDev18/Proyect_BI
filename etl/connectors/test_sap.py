# connectors/test_sap.py — prueba de conectividad de SOLO LECTURA contra SAP SQL Anywhere.
# Usa el mismo conector del pipeline (SQLAnywhereConnector), por lo que valida la ruta
# real de conexión en ambos entornos:
#   - Host Windows:  DB_DRIVER nativo ("SQL Anywhere NN")  → cadena ENG/DBN/Links
#   - Contenedor:    DB_DRIVER=FreeTDS (docker-compose.yml) → cadena Server/Port/TDS 5.0
# Ejecutar en Docker:  docker compose run --rm etl python connectors/test_sap.py
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from config.settings import ETLConfig
from connectors.sqlany_connector import SQLAnywhereConnector


def test_connection() -> bool:
    cfg = ETLConfig()
    sap = SQLAnywhereConnector(cfg)
    masked = sap._conn_str.replace(cfg.DB_PASSWORD, "***") if cfg.DB_PASSWORD else sap._conn_str
    print(f"Driver: {cfg.DB_DRIVER}")
    print(f"Cadena de conexión: {masked}")
    try:
        sap.connect()
        df = sap.query_to_dataframe('SELECT TOP 1 * FROM "dbo"."kardex"')
        print(f"[OK] Conexión exitosa a Producción (SELECT de solo lectura, {len(df)} fila).")
        return True
    except Exception as e:
        print(f"[Error] de conexión: {e}")
        return False
    finally:
        sap.disconnect()


if __name__ == "__main__":
    print("Probando conexión hacia SAP SQL Anywhere transaccional (Producción)...")
    ok = test_connection()
    sys.exit(0 if ok else 1)
