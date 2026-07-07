import pandas as pd
from sqlalchemy import create_engine

host = "localhost"
port = "5433"
user = "etl_user"
pwd  = "CHANGE_ME"
db   = "edw"

engine = create_engine(f'postgresql://{user}:{pwd}@{host}:{port}/{db}')

query = """
SELECT 
    v.nombre_vendedor as vendedor,
    d.anio,
    d.mes,
    SUM(f.subtotal_neto) as ventas,
    SUM(f.cantidad) as unidades
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
WHERE v.nombre_vendedor LIKE '%%REY%%'
GROUP BY v.nombre_vendedor, d.anio, d.mes
ORDER BY v.nombre_vendedor, d.anio, d.mes
"""
df = pd.read_sql(query, engine)
print("Ventas de Almacen el Rey (Vendedor):")
pd.set_option('display.max_rows', 100)
print(df)
