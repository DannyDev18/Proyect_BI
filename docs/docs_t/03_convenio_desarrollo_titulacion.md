# CONVENIO DE DESARROLLO TECNOLÓGICO Y TITULACIÓN

Por medio del presente convenio se establecen los términos de coordinación técnica, alcance y propiedad intelectual para el desarrollo de la **"Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal"** (en adelante, el "Proyecto"), suscrito entre la Empresa y el Desarrollador el 6 de Julio de 2026:

## 1. ALCANCE TÉCNICO Y ENTREGABLES

El Proyecto comprende el diseño de un sistema monorepo dockerizado estructurado por los siguientes componentes técnicos:

1.  **Mecanismo de Extracción y Carga (ETL):** Scripts en Python (`etl/orchestrator.py`) que migran del ERP origen SAP SQL Anywhere a Postgres de manera incremental con seudonimización nativa HMAC-SHA256 (`PII_SALT`).
2.  **Base de Datos Analítica (OLAP Data Warehouse):** Esquema relacional `edw` en PostgreSQL estructurado bajo una Constelación de Hechos (`edw.Fact_Ventas_Detalle`, `edw.Fact_Inventario_Snapshot`, `edw.Fact_Metas_Comerciales`) y dimensiones conformadas (`Dim_Cliente`, `Dim_Producto`, `Dim_Sucursal`, `Dim_Vendedor`, `Dim_Fecha`) tolerando SCD Tipo 2.
3.  **Modelos de Inferencia (Machine Learning):** Pipellines y binarios de estimación serializados con Joblib en `ml/models/` para predicción de ventas (Random Forest Regressor), estimación de demanda semanal por SKU, agrupamiento de perfiles de clientes (K-Means para segmentación RFM), y propensión de fuga (XGBoost/Random Forest Classifier).
4.  **Capa de Servicios REST (FastAPI):** Backend en Python estructurado en tres capas (Routers, Services con Hydration Engine, y CRUD DB) que unifica el control de acceso JSON Web Tokens y roles jerárquicos (RBAC).
5.  **Capa de Presentación (React SPA):** Interfaz unificada en React 19 con soporte Vite y diagramas informativos en Recharts con accesos restringidos para perfiles de Gerente, Bodega, Venta y Administrador.

---

## 2. EXCLUSIONES OPERATIVAS EXPRESAS (LÍMITE DE ALCANCE)

Las Partes acuerdan expresamente que el Proyecto tiene fines analíticos e investigativos (Business Intelligence) y **no comprende**:

- Modificaciones, inserciones de datos o alteraciones de esquemas dentro de la base de datos transaccional origen (SAP SQL Anywhere) o sistema ERP de la Empresa.
- Automatización de procesos operacionales o flujos transaccionales reales de facturación o contabilidad.
- Garantizar la conectividad física de redes o adquisición de hardware e infraestructura de servidores de producción de la Empresa.

---

## 3. PROPIEDAD INTELECTUAL

El régimen aplicable al código fuente y metodologías resultantes se regirá bajo las siguientes directrices:

1.  **Derechos Morales (Autoría):** El Desarrollador retendrá en todo momento de forma exclusiva la autoría moral e intelectual sobre los algoritmos, código fuente desarrollado y la metodología general del Proyecto, teniendo derecho a ser mencionado y presentar el Proyecto en el ámbito universitario para la obtención de su título académico.
2.  **Derechos Patrimoniales (Licencia de Uso):** La Empresa obtendrá de forma exclusiva una **Licencia de Uso no exclusiva, a perpetuidad, intransferible y libre de regalías (Royalty-free)** para ejecutar, desplegar y explotar comercialmente el Proyecto dentro de sus operaciones comerciales internas mundiales. La Empresa no podrá sublicenciar, revender o empaquetar comercialmente el código fuente de forma independiente a terceros sin consentimiento expreso por escrito del Desarrollador.

---

## 4. CLÁUSULA DE RESPONSABILIDAD LIMITADA (AS-IS / COMO ESTÁ)

1.  **Naturaleza Probabilística:** El Desarrollador hace costar que los modelos de Machine Learning (por ejemplo, predicción de ventas con Random Forest, clasificación de riesgo de abandono de clientes) proveen exclusivamente de **proyecciones estadísticas y estimaciones probabilísticas** basadas en comportamientos históricos de datos provistos por la Empresa.
2.  **Sin Garantía de Resultados Exactos:** El Desarrollador entrega los componentes analíticos bajo el principio legal "AS-IS" (como está) y no asume ninguna responsabilidad civil, administrativa o pecuniaria en el supuesto de que las estimaciones predictivas diverjan de la realidad comercial o de ventas de la Empresa. La toma de decisiones empresariales basadas en las predicciones del sistema es de exclusiva responsabilidad comercial de los gerentes y personal de la Empresa.

---

## 5. FIRMA Y CONSTANCIA

Estando las partes de acuerdo con todas las secciones de este convenio, firman en la fecha y lugar registrados en las firmas principales.

```
__________________________________             __________________________________
[Representante Legal de la Empresa]            [Desarrollador / Investigador]
Representante de la Empresa                    Estudiante / Desarrollador
[Nombre de la Empresa]                         C.C. [Número de Cédula]
```
