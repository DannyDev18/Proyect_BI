# DOCUMENTACIÓN TÉCNICA Y ARQUITECTURA CORE
**Proyecto:** Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal.
**Estado:** Fase de Integración y Depuración (Backend ↔ ML ↔ Frontend).

---

## 1. ARQUITECTURA GENERAL (N-Capas)

La plataforma adopta una arquitectura de datos moderna desacoplada para garantizar el rendimiento operacional (OLTP) y la capacidad de inferencia estadística (OLAP/ML).

1. **Capa OLTP:** SAP SQL Anywhere (Fuente de lectura de facturación, inventarios y nómina).
2. **Capa ETL (Python):** Orquestador de ingesta incremental y seudonimización criptográfica (SHA-256 + Salt) para cumplimiento estricto de la LOPDP.
3. **Capa OLAP (PostgreSQL):** Data Warehouse modelado en Constelación de Hechos (`fact_ventas_det`, `fact_inventario_snapshot`) con Dimensiones de Variación Lenta (SCD Tipo 2). *(Ver `arquitectura_dw.md` para DDL y esquemas).*
4. **Capa MLOps:** Entorno aislado de entrenamiento que exporta binarios (`.pkl` / `.joblib`) de regresión y clasificación.
5. **Capa Backend (FastAPI):** API RESTful que ejecuta la inferencia en memoria, hidrata datos seudonimizados y protege endpoints mediante JWT y RBAC.
6. **Capa Frontend (React/Vite):** SPA protegida con dashboards segmentados por rol.

---

## 2. ESPECIFICACIÓN: DASHBOARD DE GERENCIA Y PREDICCIONES (KPIs)

Este módulo es el núcleo estratégico. El backend debe calcular métricas históricas de la base de datos y fusionarlas con inferencias de los modelos `.pkl`.

### 2.1 Cálculo de KPIs Históricos (Tiempo Real)
El servicio de FastAPI debe exponer endpoints (ej. `/api/v1/analytics/kpis`) que ejecuten consultas relacionales para obtener:
* **Margen de Utilidad Neta ($M$):**
  $$M = \frac{\text{Ventas Netas Totales} - \text{Costo Total de Ventas}}{\text{Ventas Netas Totales}} \times 100$$
* **Ticket Promedio ($TP$):**
  $$TP = \frac{\sum \text{Monto Neto Transacciones}}{\text{Cantidad Total de Transacciones Únicas}}$$

### 2.2 Integración de Predicciones (Machine Learning)
El backend consume el modelo entrenado (XGBoost/CatBoost o Random Forest) para generar el gráfico de tendencias.
* **Flujo de Inferencia:** El endpoint de predicción recibe el rango de fechas solicitado por el frontend, construye un DataFrame con los *features* esperados (ej. lags históricos, día de la semana, festivos) y ejecuta `.predict()`.
* **Estructura de Respuesta Esperada por React:**
  Para evitar errores de renderizado en `Recharts`, el backend debe devolver un array estricto de objetos JSON:
  `[{ "fecha": "2026-07-08", "venta_real": null, "venta_proyectada": 15420.50 }, ...]`

---

## 3. ESPECIFICACIÓN: MÓDULO DE METAS Y COMISIONES COMERCIALES

El sistema automatiza la compensación variable evaluando el rendimiento real contra objetivos corporativos.

### Lógica de Negocio y Cálculo (Backend)
Las metas se almacenan en `edw.fact_metas_comerciales`. El motor de FastAPI (en `analytics_service.py` o `goals.py`) calcula el avance así:

1. **Porcentaje de Logro ($%L$):**
   $$\%L_{v,m} = \left( \frac{\text{Ventas Netas del Vendedor en el Mes}}{\text{Meta Asignada al Vendedor en el Mes}} \right) \times 100$$

2. **Cálculo de Comisión Asignada:**
   $$\text{Comisión} = \text{Ventas Netas} \times \text{Factor}$$
   Donde el factor depende del escalafón de rendimiento:
   * Si $\%L < 90\% \Rightarrow \text{Factor} = 0.00$
   * Si $90\% \le \%L < 100\% \Rightarrow \text{Factor} = 0.01$
   * Si $\%L \ge 100\% \Rightarrow \text{Factor} = 0.02$

*(Nota para depuración: Validar que el ETL esté cruzando correctamente el `vendedor_sk` entre las ventas y las metas).*