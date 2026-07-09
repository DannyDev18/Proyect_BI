# Hoja de Ruta de Ejecución: Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas

> **Proyecto de Tesis:** Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal  
> **Arquitectura:** SAP SQL Anywhere → ETL Python → EDW PostgreSQL → FastAPI → React/TypeScript  
> **Versión del Plan:** 2.0 (Actualizada para Sprint de Despliegue)
> **Estado Actual:** Transición Fase 5 (Frontend) ➔ Fase 6 (Despliegue)

---

## Estado General del Proyecto

- [x] **Fase 1:** Configuración del Entorno y Arquitectura Base
- [x] **Fase 2:** Ingeniería de Datos (ETL y Data Warehouse)
- [x] **Fase 3:** Ciencia de Datos y Machine Learning _(Completado: 7 modelos entrenados y dockerizados)_
- [x] **Fase 4:** Desarrollo del Backend (FastAPI) _(Completado: Integrados modelos ML, endpoints, y base RBAC)_
- [x] **Fase 5:** Desarrollo del Frontend (React/TypeScript) _(Completado: Dashboards, metas, SPA con Zustand)_
- [~] **Fase 6:** Despliegue e Integración Continua _(EN PROGRESO)_
- [ ] **Fase 7:** Documentación y Validación de la Tesis _(En revisión final)_

---

<a name="fase-3"></a>

## Fase 3: Ciencia de Datos y Machine Learning (COMPLETADO)

> **Objetivo Alcanzado:** Finalizado el entrenamiento (Pandas/SQLAlchemy), feature engineering optimizado y exportación exitosa de los binarios (`.pkl`) competidores (XGBoost, RandomForest, IsolationForest, K-Means, Apriori) a la carpeta backend para su consumo.

---

<a name="fase-4"></a>

## Fase 4: Desarrollo del Backend (FastAPI) (COMPLETADO)

> **Objetivo Alcanzado:** Endpoints de la API levantados exitosamente, JWT funcionando bajo esquema RBAC (Gerencia, Vendedor, Bodeguero, Admin). Inferencia exitosa de los modelos ML implementada.

---

<a name="fase-5"></a>

## Fase 5: Desarrollo del Frontend (React / TypeScript) (COMPLETADO)

> **Objetivo Alcanzado:** SPA React con dashboards dinámicos funcionando en tiempo real consumiendo la API REST con interceptores JWT. Mapeo de vistas separadas para Gerente y Consola de Metas, y Bodega operativa listos y renderizando UI moderna.

---

<a name="fase-6"></a>

## Fase 6 y 7: Despliegue y Tesis (PLANIFICADO)

- **Despliegue:** Contenerización final para producción (Nginx, Gunicorn), configuración de crontab para el ETL y SSL.
- **Tesis (Redacción):** Traslado de la documentación técnica en `docs/` al formato institucional, extracción de métricas de precisión de los modelos (R², MAE, ROC-AUC) y preparación de la defensa.

---

_Documento mantenido activamente para sincronización del equipo de desarrollo._
