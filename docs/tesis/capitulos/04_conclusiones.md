# CAPÍTULO IV. CONCLUSIONES Y RECOMENDACIONES

## 4.1 Conclusiones

1. El análisis de la estructura y calidad de los datos del sistema transaccional ERP (SAP SQL Anywhere 17) confirmó que dicho sistema, optimizado para el procesamiento de transacciones de alta concurrencia, carece de la capacidad de sostener consultas analíticas multidimensionales, validando empíricamente la necesidad de un repositorio analítico independiente planteada en el problema de investigación (objetivo específico 1).

2. El proceso ETL diseñado e implementado extrae, transforma y carga la información del ERP hacia el Data Warehouse de forma incremental e idempotente, evitando la duplicación de registros ante reejecuciones y preservando el historial de cambios de productos y clientes mediante dimensiones de variación lenta de tipo 2, lo que garantiza la trazabilidad temporal exigida por el análisis histórico multidimensional (objetivo específico 2).

3. El Data Warehouse construido bajo el enfoque dimensional de Kimball consolidó, al cierre del desarrollo documentado, 538 862 registros de venta de detalle y aproximadamente 948 000 movimientos de inventario en un modelo de once dimensiones conformadas y once tablas de hechos, demostrando que es posible estructurar en una constelación de hechos coherente la operación de una empresa multisucursal originada en un ERP que no distingue analíticamente entre sus sucursales de forma nativa (objetivo específico 3).

4. La API backend desarrollada expone la información y las predicciones de forma diferenciada por rol mediante autenticación JWT y control de acceso basado en roles (RBAC), arquitectura que además de resolver el requerimiento funcional de segmentación por rol, permitió detectar y corregir durante el desarrollo una fuga real de control de acceso que exponía información de clientes fuera de la cartera del vendedor autenticado, evidenciando el valor de una arquitectura de permisos explícita y auditable frente a un control de acceso implícito (objetivo específico 4).

5. De los seis modelos de Machine Learning entrenados y evaluados, el de predicción de demanda de reposición de inventario alcanzó el desempeño más sólido (R² = 0.959), mientras que el de predicción de ventas, tras la corrección de la ventana de entrenamiento, alcanzó un desempeño moderado pero utilizable (R² = 0.297); el modelo de segmentación de clientes produjo agrupamientos matemáticamente cohesivos (silueta = 0.612) y el de riesgo de abandono una capacidad discriminativa aceptable aunque mejorable (AUC-ROC = 0.701). En conjunto, estos resultados confirman que los datos históricos de la operación contienen señal predictiva aprovechable, en grados distintos según la naturaleza de cada variable objetivo (objetivo específico 5).

6. Los dashboards web desarrollados, segmentados por los cuatro roles de negocio de la organización, integran los indicadores clave de desempeño y las predicciones generadas por los modelos directamente en el flujo operativo de cada rol —no solo en reportes gerenciales de cierre de período—, materializando el enfoque de inteligencia de negocios operacional descrito en el marco teórico (objetivo específico 6).

7. La plataforma demostró su utilidad como herramienta de apoyo a la toma de decisiones al identificar y corregir, durante su propio proceso de desarrollo y auditoría continua, defectos funcionales reales que habrían impedido su uso efectivo —incluyendo un indicador principal del dashboard de Ventas que retornaba error en el 100 % de las solicitudes—, lo que sustenta la pertinencia del proceso de validación adoptado (auditoría técnica documentada más pruebas automatizadas) como mecanismo de aseguramiento de calidad para este tipo de sistemas (objetivo específico 7).

8. En conjunto, los resultados obtenidos responden afirmativamente a la pregunta de investigación planteada en 1.1.1: el diseño e implementación de la plataforma inteligente de analítica empresarial, sustentada en un Data Warehouse dimensional y en modelos de Machine Learning, transformó los datos transaccionales dispersos de la empresa multisucursal objeto de estudio en información estratégica y predicciones accesibles de forma diferenciada por rol de usuario.

## 4.2 Recomendaciones

1. Ampliar la ventana de variables exógenas disponibles para el modelo de predicción de ventas —en particular, poblar `dim_fecha.es_feriado` de forma sistemática en el proceso ETL en lugar de mantener la aproximación de feriados como una lista codificada dentro del pipeline de Machine Learning— con el fin de reducir la duplicación de lógica entre capas y explorar si una señal de feriados más completa (incluyendo los móviles ya incorporados y su fuente centralizada en el Data Warehouse) mejora el R² actual de 0.297.

2. Evaluar la incorporación de variables exógenas adicionales para el modelo de riesgo de abandono de clientes, dado que su AUC-ROC de 0.701, si bien aceptable, deja margen de mejora frente a los resultados reportados en la literatura revisada (por ejemplo, Fauzi et al., 2026, que alcanzaron una exactitud de 84.88 % y un AUC-ROC de 0.9294 con variables contractuales no disponibles en el dominio comercial de este proyecto), explorando en particular variables de recencia de interacción y de comportamiento de pago de cartera.

3. Investigar la afinidad de venta cruzada por sucursal como una extensión del modelo de recomendación actual, dado que el análisis exploratorio documentado durante el desarrollo evidenció una afinidad de coocurrencia de productos fuertemente local entre sucursales (sin intersección en los pares más frecuentes de las dos sucursales de mayor volumen), lo que sugiere que un modelo único global, como el actualmente en producción, podría estar promediando patrones de compra que en realidad son distintos entre puntos de venta.

4. Poblar la dimensión de geografía (`dim_geografia`), actualmente vacía, para habilitar análisis territoriales que hoy no son posibles pese a que el modelo dimensional ya contempla dicha dimensión conformada.

5. Establecer un calendario formal de reentrenamiento periódico de los modelos de Machine Learning contra el Data Warehouse actualizado, dado que las métricas reportadas en este documento corresponden a un corte específico del histórico y la operación comercial continúa generando datos nuevos que podrían modificar el desempeño de los modelos con el tiempo.

6. Formalizar, en un trabajo de titulación o ciclo de desarrollo posterior, una fase de validación con usuarios finales reales de cada rol (gerencia, ventas, bodega, administración) mediante instrumentos de recolección directa (entrevistas o encuestas estructuradas), complementando la validación técnica documentada en este proyecto con evidencia de aceptación desde la perspectiva del usuario de negocio, instrumento que no se aplicó dentro del alcance de la presente investigación.

---

## Notas de trazabilidad (no forma parte del cuerpo entregable — eliminar antes de la versión final)

- Las conclusiones se redactaron respondiendo uno a uno a los 7 objetivos específicos de 1.4.2 y a la pregunta de investigación de 1.1.1, sin introducir hallazgos nuevos no presentados en el capítulo de Resultados (regla de consistencia objetivos-resultados-conclusiones verificada manualmente; se recomienda pasar thesis-reviewer para una verificación formal).
- Recomendación 2 cita la cifra de AUC-ROC=0.929 de Fauzi et al. (2026) — verificar que esa cifra específica (no solo la exactitud del 84.88% y AUC=92.94% ya citados en 1.2) esté correctamente extraída de la fuente antes de la entrega final; si no se puede confirmar el dato exacto de AUC como número aparte de lo ya verificado, ajustar la redacción para no sobre-especificar.
- Las recomendaciones 1, 3 y 4 se basan en limitaciones documentadas explícitamente como reales en `ml/REPORTE_MEJORA_MODELOS.md` (feriados móviles, afinidad de venta cruzada por sucursal) y en `CLAUDE.md` (`dim_geografia` vacía, hallazgo abierto de la auditoría 05) — no son sugerencias genéricas.
- Pendiente: este capítulo no incluye la sección de Referencias Bibliográficas (compilación final de las 10 fuentes citadas) ni Anexos — se redactan por separado.
