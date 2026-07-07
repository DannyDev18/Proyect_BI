import os
import sys
sys.path.append(os.path.dirname(__file__))

from connectors.sqlany_connector import SQLAnywhereConnector
from config.settings import ETLConfig
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

cfg = ETLConfig()
sap = SQLAnywhereConnector(cfg)
try:
    sap.connect()
import pandas as pd

try:
    sap.connect()
    print("==== TABLAS CON NOTA, CREDITO O DEV ====")
    # En SQL Anywhere, sysobjects o sys.systable
    # Vamos a probar systable
    df = pd.read_sql("SELECT table_name FROM sys.systable WHERE table_name LIKE '%nota%' OR table_name LIKE '%credito%' OR table_name LIKE '%dev%'", sap._conn)
    print(df)
finally:
    sap.disconnect()
