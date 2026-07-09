# UI/UX Specifications: Dashboards de Bodega y Gerencia

## 1. Problema que Resuelve

El ERP transaccional está diseñado para el día a día operativo pero no entrega pantallas de control (Business Intelligence). Se requiere que los diferentes niveles estratégicos y operativos visualicen los KPIs procesados por el backend en interfaces de un solo vistazo y en tiempo real.

## 2. Dashboard Gerencial (Executive Board)

### 2.1 Definición y Audiencia

Dashboard de alto nivel orientado al **Gerente General** o al **Administrador Financiero**.
El objetivo es priorizar rentabilidad sobre movimientos físicos de caja diarios.

### 2.2 Fuentes y KPIs Indicados

- **Rentabilidad Corporativa (Net Revenue / Gross Margin):** Extracción de `Fact_Ventas_Detalle` consolidada, comparada mediante `% KPI` YOY (Año tras Año). Sumatoria excluyendo anulados y devoluciones.
- **Top Desempeño Ventas y Predicción (Ventas Previstas ML):** Utiliza los resultados del modelo predictivo (`/api/v1/kpis/gerencia` > Sales Forecast) cruzándolos con la meta de ventas mensual. Visualización mediante Dual Series Area Chart.
- **Top Sucursales y Distritos:** Concentración porcentual de ventas en un Pareto geográfico para decisiones de expansión.
- **Salud del Inventario Estratégico:** Indicador macro valorizado en dólares (Cuántos miles de dólares están estancados sin rotación de acuerdo a la segmentación del data warehouse).

## 3. Dashboard Cadenas Suministro (Bodega/Hub)

### 3.1 Definición y Audiencia

Pantalla especializada para el **Jefe Comercial Logístico** enfocado localmente en el centro operativo/bodega matriz (`Atahualpa`). Prioridad física operativa sobre valorización nominal.

### 3.2 Fuentes y KPIs Indicados

- **Monitoreo de Stock out Inminente:** Panel directo (Tabla o Tarjetas Rojas) leyendo bandera `alerta_desabastecimiento` y `dias_abastecimiento_cob` desde `Fact_Inventario_Snapshot`.
- **Exceso de Inventario / Inmovilizado:** Extracción de artículos cuya bandera `inmovilizado_flag = TRUE` que deban redistribuirse en camiones, mostrando el número de meses ocioso en estante local.
- **Traslados en Vuelo / Pedidos Restantes:** Cantidad general del mes requerida para reposición (`y_demanda_sugerida`).
- **Rotación Kárdex del Día:** Tabla continua que muestre picos de entradas/salidas inusuales (cruce con detector de anomalías) leyendo la tabla analítica estructurada de los Extractores.

## 4. Control de Acceso (RBAC) e Integraciones

Ambos módulos estarán encapsulados en el Frontend (React) a través del manejador global de estado (Zustand + JWT).

- Gerencia **ve todo** pero **no edita/traspasa stock**.
- Bodega **ve su local** y las órdenes del modelo ML (reposiciones sugeridas), pero **no ve utilidades líquidas, márgenes financieros (ocultos los campos de costo por roles) ni comisiones de los agentes comerciales.**
