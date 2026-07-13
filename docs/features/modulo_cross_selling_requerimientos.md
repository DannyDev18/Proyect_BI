# Requerimientos — Módulo de Venta Cruzada (Cross-Selling)

> Documento de requerimientos entregado por el usuario el 2026-07-13.
> Objetivo general: módulo de recomendación de productos (venta cruzada) integrado
> end-to-end en la plataforma (EDW → ML → FastAPI → React), con sugerencias para el vendedor.

## FASE 0: Análisis y comprensión del proyecto actual

Objetivo: entender la arquitectura, datos y flujo del sistema para identificar cómo y dónde integrar el nuevo módulo.

- **Auditoría de la base de datos** (origen SAP): tablas de hechos `renglonesfacturas`, `encabezadofacturas`, `kardex`; dimensiones `articulos`, `clientes`, `vendedores`; relaciones/FKs; volumen de datos (registros históricos, clientes y productos únicos).
- **Entendimiento del EDW actual**: modelo dimensional existente, estructura de `Fact_Ventas_Detalle` y dimensiones, transformaciones origen → EDW.
- **Identificación del flujo de la aplicación**: cómo interactúa el vendedor con el sistema, en qué momento mostrar la sugerencia, comunicación backend (FastAPI) ↔ frontend.

**Entregable Fase 0:** documento con diagrama ER de tablas relevantes, mapeo origen → EDW, descripción del flujo de la aplicación y punto de integración.

## FASE 1: Estrategia de venta cruzada y definición de requerimientos

- **Objetivo del modelo:** predecir la probabilidad de que un cliente compre un producto adicional; decidir qué productos sugerir (populares, comprados juntos, mayor margen).
- **Estrategia de recomendación:** reglas de asociación (Apriori), filtrado colaborativo, basada en contenido, o híbrido (recomendado).
- **Formato de la sugerencia:** cuántos productos (Top 3–5); qué información mostrar al vendedor (nombre, precio, beneficio estimado, razón tipo "clientes que compraron X también compraron Y").

**Entregable Fase 1:** documento con estrategia seleccionada y justificación; requisitos funcionales y no funcionales.

## FASE 2: Preparación de datos para el modelo de ML

- **Extracción:** transacciones (`num_factura`, `codcli`, `fecfac`), detalle de ventas (`codart`, cantidad, precio), catálogo de productos (`codart`, nombre, `codgrupo`, precio) — desde el EDW.
- **Transformación:** agrupar por cliente (lista de productos comprados), matriz de co-ocurrencia por par de productos, atributos adicionales (frecuencia de compra, ticket promedio, margen, estacionalidad).
- **Limpieza:** nulos (productos sin categoría), transacciones anómalas o de prueba, formato adecuado para ML.

**Entregable Fase 2:** scripts Python (pandas) de extracción/transformación; dataset procesado listo para entrenamiento.

## FASE 3: Diseño, entrenamiento y validación del modelo

- **Opción A (recomendada para empezar):** reglas de asociación con Apriori (mlxtend): itemsets frecuentes, reglas con Soporte/Confianza/Lift, filtrar por Lift alto.
- **Opción B:** filtrado colaborativo (matriz cliente × producto; SVD o KNN).
- **Opción C:** modelo híbrido (asociación + contenido) a largo plazo.
- **Entrenamiento y validación:** split 80/20; métricas Precision@K y Recall@K; métricas de negocio (impacto en ticket promedio).
- **Almacenamiento:** modelo/reglas serializados con joblib/pickle.

**Entregable Fase 3:** código de entrenamiento y validación, `.pkl` del modelo, reporte de métricas.

## FASE 4: Integración y despliegue (backend)

- Motor de recomendación (`recommendation_engine.py`): carga del modelo al iniciar FastAPI; función que dado un `codart` (y opcionalmente `codcli`) retorna productos sugeridos.
- Nuevo endpoint (ej. `POST /recomendar_productos`) que recibe el producto en compra y devuelve JSON con sugerencias (código, nombre, precio).
- Heurísticas de negocio: filtrar productos ya comprados por el cliente, priorizar mayor margen, limitar a 3–4 sugerencias.

**Entregable Fase 4:** motor de recomendación, endpoint nuevo, pruebas del endpoint.

## FASE 5: Integración y despliegue (frontend)

- Identificar punto de integración en la UI (pantalla de venta / panel lateral).
- Llamada al endpoint desde el frontend al agregar un producto.
- Componente de UI con nombre, precio y botón "Agregar" para añadir la sugerencia con un clic.

**Entregable Fase 5:** código frontend de sugerencias; pruebas de integración end-to-end.

## FASE 6: Monitoreo, mantenimiento y mejora continua

- **Monitoreo:** registrar sugerencias mostradas vs aceptadas; tasa de conversión como KPI principal.
- **Ciclo de actualización:** reentrenamiento periódico (semanal/mensual) con nuevos datos de ventas.
- **Mejora iterativa:** otros algoritmos, más datos (hora, ubicación), pruebas A/B.

**Entregable Fase 6:** script/scheduler de reentrenamiento; tablero/reporte de KPIs del módulo.

## Entregables finales esperados

1. Código fuente completo (motor de recomendación, endpoint FastAPI, frontend).
2. Modelo entrenado (`.pkl` / reglas generadas).
3. Documentación: instrucciones de reentrenamiento, guía de uso para el vendedor, diagrama de arquitectura del módulo.
4. Pruebas: reporte de pruebas y métricas de rendimiento del modelo.
