# Especificación de Dominio: Segmentación Cliente-Valor (RFM & Machine Learning)

## 1. Problema que Resuelve

Los gerentes de ventas carecen de visibilidad sobre cuáles clientes son clave (alto portafolio, alta retención) frente a aquellos que están en riesgo de abandono definitivo. Tratar a todos los clientes por igual resulta en una pérdida de oportunidades de campañas fidelizantes y desperdicio de recursos comerciales.

## 2. Definición del Modelo y Objetivos

- **Objetivo Predictivo/Clasificatorio:** Agrupar clientes automáticamente en _Clústers de Valor_ o nichos de comportamiento en base a parámetros RFM sin necesidad de colocar reglas humanas subjetivas.
- **Consumidores del Modelo:** Gerencia, Vendedores VIP, Campañas de Marketing.
- **Algoritmo Base:** Modelos de Clustering No Supervisados (K-Means, DBSCAN) sobre matrices RFM normalizadas.

## 3. Arquitectura del Flujo de Datos

### 3.1 Entrada (Fuentes de Datos)

La información base proviene del EDW PostgreSQL:

- **`Fact_Ventas_Detalle` / `Kardex`**: Para rastreo económico.
- **`Dim_Cliente`**: Demografía.

### 3.2 Proceso ETL y Transformación (`ml/src/data/make_dataset.py`)

Features Críticos (Matrices RFM Transformadas):

- **Recency (R)**: Tiempo transpuesto en días desde la última factura procesada a ese código de cliente.
- **Frequency (F)**: Conteo total de boletas o facturas distintas en un periodo determinado (ej. últimos 365 días).
- **Monetary (M)**: Sumatoria del volumen en USD pagado históricamente (Monto Bruto menos Notas de Crédito).

_Nota ETL_: Para Machine Learning, esta matriz debe escalarse estructuralmente (Ej. `StandardScaler`) dado que "días" vs "miles de dólares" tienen desproporciones numéricas que arruinan la densidad vectorial de K-Means.

### 3.3 Entrenamiento y Salida (Clustering)

- **Extracción ML**: Se itera el Método del Codo (Elbow Score) o Silhouette Index durante el entrenamiento automatizado para seleccionar si existen `K=3`, `4` o `5` segmentos base naturales en la empresa.
- **Artefactos Resultantes**: El modelo de K-Means guardado que retiene los centroides (`customer_segmentation_model.pkl`).

## 4. Dependencias del Backend e Integración (API FastAPI)

| Flujo Funcional        | Detalle                                                                                                                                                                                                                                                                                  |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Programación Batch** | A diferencia del cross-selling que ocurre "en vivo", los perfiles RFM son procesados estáticamente cada domingo de madrugada.                                                                                                                                                            |
| **Volcado SQL**        | El orquestador predice el grupo de todo el catálogo de clientes de golpe y lo persiste directamente (Write-back) como un campo nuevo (ej. `Segmento_IA = "Frecuente Inactivo"`) dentro de la dimensión `Dim_Cliente` en la tabla SQL de PostgreSQL.                                      |
| **Reporte de Ventas**  | Los vendedores ven esta insignia estática al buscar el registro del cliente corporativo.                                                                                                                                                                                                 |
| **API Churn Risk**     | Se interconecta un modelo secundario de Churn (abandono). El backend expone en una vista especial la lista de "Clientes de Alto Valor que no han comprado en 60 días" ordenados descendentemente por su probabilidad de fuga (usando Regresión Logística sobre el mismo target K-Means). |

## 5. Prioridad y Jerarquía

- **Prioridad Estratégica**: MEDIA/ALTA (Retención empresarial).
- **Consumo Subsecuente**: La segmentación actúa como **filtro primario**; el cruce de ventas o metas comerciales puede parametrizarse para diferenciar bonificaciones en base al segmento objetivo (`Target Customer`).
