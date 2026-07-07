import os
import pyodbc
from sqlalchemy import create_engine
from dotenv import load_dotenv

# 1. Cargar las variables del archivo .env
# Esto requiere python-dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# 2. Leer las variables de entorno
DB_DRIVER = os.getenv("DB_DRIVER", "SQL Anywhere 12")
DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

# 3. Construir la cadena de conexión
CONN_STR = (
    f"Driver={{{DB_DRIVER}}};"
    f"ENG={DB_SERVER};"
    f"DBN={DB_DATABASE};"
    f"UID={DB_USER};"
    f"PWD={DB_PASSWORD};"
)

if DB_HOST and DB_PORT:
    CONN_STR += f"Links=tcpip(Host={DB_HOST};Port={DB_PORT});"

def test_connection():
    """Prueba la conexión directa con pyodbc."""
    try:
        conn = pyodbc.connect(CONN_STR)
        if conn:
            cursor = conn.cursor()
            cursor.execute('SELECT TOP 1 * FROM "dbo"."kardex"')
            cursor.fetchone()
            conn.close()
            print("[OK] Conexión exitosa a la base de datos origen en SAP")
            return True
        return False
    except Exception as e:
        print(f"[Error] de conexión (pyodbc nativo): {e}")
        return False

if __name__ == "__main__":
    print("Probando conexión hacia SAP SQL Anywhere transaccional (Producción)...")
    test_connection() 
