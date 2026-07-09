# Especificación de Dominio: Predicción de Ventas (Machine Learning)

## 1. Problema que Resuelve

La empresa requiere pronosticar con precisión los ingresos (ventas netas) y el volumen de productos que comercializará en períodos futuros. Esto es crítico para la gestión de flujo de caja, planeación de importaciones y asignación de presupuestos trimestrales.

## 2. Definición del Modelo y Objetivos

- **Objetivo Predictivo:** Pronosticar el valor total (USD) y la cantidad de unidades (`y_sales_net`, `y_quantity`) que se venderán por diferentes dimensionalidades (Día, Semana, Mes, Sucursal, Vendedor, Categoría).
- **Consumidores del Modelo:** Dashboard Gerencial (proyecciones de finanzas corporativas).
- **Algoritmo Base:** `XGBoostRegressor` / `RandomForest` / `LightGBM` (Competición y selección automática).

## 3. Arquitectura del Flujo de Datos

### 3.1 Entrada (Fuentes de Datos)

La información base proviene del EDW PostgreSQL:

- **`Fact_Ventas_Detalle`**: Ventas históricas y cantidades a nivel renglón.
- **`Dim_Fecha`**: Estacionalidades (feriados, fin de semana, meses).
- **`Dim_Sucursal`**: Comportamiento aislado territorial.
- **`Dim_Producto` / `Dim_Linea`**: Ventas por categorías o grupos de artículos.

### 3.2 Proceso ETL y Transformación (`ml/src/data/make_dataset.py`)

Variables (Features) a construir para el entrenamiento y la inferencia:

- **Agrupaciones Temporales**:
  - Subtotales diarios, semanales y mensuales historizados por sucursal / vendedor.
- **Lags (Rezagos Temporales)**:
  - Ventas del mismo día la semana anterior (`Lag_7`).
  - Ventas del mismo mes el año anterior (`Lag_YOY`).
- **Rolling Windows (Promedios Móviles)**:
  - Promedio móvil de 7, 30 y 90 días para capturar la tendencia de la demanda real.
- **Estacionalidad (Encoding Temporal)**:
  - Funciones trigonométricas (Seno/Coseno) extraídas de mes y día para predecir picos cíclicos periódicos de compras.

### 3.3 Entrenamiento y Salida (Output)

- **Frecuencia de Entrenamiento**: Retraining automatizado mediante orquestador cada semana.
- **Salida / Target del modelo**: `y_sales_net` - Predicción de la recaudación neta (en USD).
- **Artefactos Resultantes**: Archivo binario serializado (Ej. `sales_prediction_model.pkl`) en `/ml_models`.

## 4. Dependencias del Backend e Integración (API FastAPI)

El servicio predictivo (`backend/app/services/analytics.py`) procesará estas series para servirse a la vista de gerencia.

| Flujo Funcional       | Detalle                                                                                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Consumo ETL**       | Sistema SAP origina facturación (Kardex) -> ETL limpia y dimensiona `Fact_Ventas`                                                                                            |
| **Entrenamiento**     | `ml/main.py` lee agregados, entrena modelo de ventas y exporta `.pkl` en el backend                                                                                          |
| **Inferencia Web**    | Frontend hace GET `api/v1/kpis/gerencia`. Backend genera un DataFrame del histórico del último mes, añade las features y llama a `model.predict()` para proyectar mes actual |
| **Consumo Dashboard** | `DashboardGerencia.tsx` expone gráfica ECharts dual (Gráfico de Área: Ventas pasadas vs. Línea Proyectada: Forecasting ML).                                                  |

## 5. Prioridad y Estado

- **Prioridad Funcional**: CRÍTICA (Nivel Gerencial).
- **Frecuencia de Actualización**: La base de datos es diaria. La inferencia ocurre en tiempo real durante demanda del API.
