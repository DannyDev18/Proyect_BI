import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.analytics_service import GoalsAutomationService
import pandas as pd

engine = create_engine("postgresql://etl_user:CHANGE_ME@127.0.0.1:5433/edw")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

service = GoalsAutomationService(db)
res = service.generar_propuestas_metas(anio=2026, mes=7, factor_presion=1.1)
print(f"Generated {res} records.")

df = pd.read_sql("SELECT sucursal, id_vendedor_origen, monto_meta FROM public.metas_comerciales_operativas ORDER BY sucursal, id_vendedor_origen;", engine)
print(df.to_string())
db.close()

