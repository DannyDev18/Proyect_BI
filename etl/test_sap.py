import os
import sys
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
sys.path.append(os.path.dirname(__file__))

from connectors.sqlany_connector import SQLAnywhereConnector
from config.settings import ETLConfig

cfg = ETLConfig()
sap = SQLAnywhereConnector(cfg)
try:
    sap.connect()
    
    df1 = pd.read_sql("SELECT TOP 1 * FROM encabezadodevoluciones", sap._conn)
    print("=== ENCABEZADO DEVOLUCIONES COLS ===")
    print(', '.join(df1.columns))
    
    df2 = pd.read_sql("SELECT TOP 1 * FROM renglonesdevoluciones", sap._conn)
    print("=== RENGLONES DEVOLUCIONES COLS ===")
    print(', '.join(df2.columns))

finally:
    sap.disconnect()
