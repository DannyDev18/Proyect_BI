FROM python:3.11-slim

WORKDIR /app

# Capa ODBC autónoma para SAP SQL Anywhere (sin depender del driver del host):
#   - unixodbc: gestor de drivers ODBC que usa pyodbc
#   - tdsodbc:  driver FreeTDS — SQL Anywhere acepta el protocolo TDS en su listener
#               tcpip (mismo mecanismo que jConnect), lo que permite un driver 100%
#               apt-instalable en lugar del cliente propietario de SAP
#   - freetds-bin: utilidades de diagnóstico (tsql) para probar conectividad
# El driver se registra en /etc/odbcinst.ini y freetds.conf fija TDS 5.0 (dialecto
# Sybase requerido por SQL Anywhere), text size amplio y conversión a UTF-8
# (el ERP almacena en cp1252). Ver docs/auditoria/06_auditoria_driver_sap_docker.md.
RUN apt-get update && apt-get install -y --no-install-recommends \
        unixodbc tdsodbc freetds-bin \
    && rm -rf /var/lib/apt/lists/* \
    && printf '[FreeTDS]\nDescription = FreeTDS Driver (SAP SQL Anywhere via TDS)\nDriver = /usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so\n' > /etc/odbcinst.ini \
    && printf '[global]\n\ttds version = 5.0\n\ttext size = 4194304\n\tclient charset = UTF-8\n' > /etc/freetds/freetds.conf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "orchestrator.py"]
