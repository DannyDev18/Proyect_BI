import sys
import os
import pandas as pd
from sqlalchemy import create_engine, text

# Conectando usando localhost (puerto mapeado desde docker)
DB_URL = "postgresql://postgres:postgres@localhost:5432/bi_dw"
engine = create_engine(DB_URL)

def run_db_audit():
    try:
        with engine.connect() as conn:
            print("--- AUDITORIA DE HISTORICO DE VENTAS ---")
            
            total = conn.execute(text("SELECT COUNT(*) FROM edw.fact_ventas_detalle")).scalar()
            print(f"Total registros fact_ventas_detalle: {total}")
            
            dates_query = """
            SELECT f.fecha_completa, SUM(v.subtotal_neto) as ventas
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            GROUP BY f.fecha_completa
            ORDER BY f.fecha_completa
            """
            df = pd.read_sql(text(dates_query), conn)
            df['fecha_completa'] = pd.to_datetime(df['fecha_completa'])
            
            print(f"Rango de fechas: {df['fecha_completa'].min().date()} a {df['fecha_completa'].max().date()}")
            print(f"Dias unicos con ventas verdaderas: {len(df)}")
            
            df.set_index('fecha_completa', inplace=True)
            df_resampled = df.resample('ME').sum() # Mensual
            print(f"Ventas por mes: \n{df_resampled}")
            
            df_d = df.resample('D').asfreq()
            missing_days = df_d[df_d['ventas'].isna()]
            print(f"Días de interrupciones (gaps sin transacciones): {len(missing_days)}")
            
            nulls = conn.execute(text("SELECT COUNT(*) FROM edw.fact_ventas_detalle WHERE subtotal_neto IS NULL")).scalar()
            print(f"Nulls en subtotal_neto: {nulls}")
            
            cero = conn.execute(text("SELECT COUNT(*) FROM edw.fact_ventas_detalle WHERE subtotal_neto = 0")).scalar()
            print(f"Valores = 0 en subtotal_neto: {cero}")
            
            duplicates = conn.execute(text("SELECT num_factura, COUNT(*) FROM edw.fact_ventas_detalle GROUP BY num_factura HAVING COUNT(*) > 50")).fetchall()
            print(f"Posibles facturas duplicadas o anomalias (mas de 50 lineas): {len(duplicates)}")
            
            out_of_seq = conn.execute(text("SELECT COUNT(*) FROM edw.fact_ventas_detalle v JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk WHERE f.fecha_completa > CURRENT_DATE")).scalar()
            print(f"Fechas futuras detectadas: {out_of_seq}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_db_audit()
