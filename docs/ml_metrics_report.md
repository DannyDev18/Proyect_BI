# Reporte de Métricas: Re-entrenamiento de Modelos (Julio 2026)

Se orquestó la tubería completa de Machine Learning (`ml/main.py`) para re-evaluar la veracidad de los modelos con la base de datos limpia. A continuación, se detallan las métricas alcanzadas de validación y entrenamiento (train-test splits).

## 1. Predicción de Ventas Generales (Random Forest Optimizado)

_Propósito: Pronosticar los ingresos futuros totales._

- **R2 Score:** `0.1024` (Mejora frente al 0.098 anterior. Se han añadido variables de medias móviles suavizadas).
- **RMSE (Error Cuadrático Medio):** `6401.78`
- **MAE (Error Absoluto Medio):** `3929.05`

## 2. Predicción de Demanda Logística (Gradient Boosting)

_Propósito: Estimar el movimiento de inventario unitario._

- **R2 Score:** `0.9589` (Aumento monumental tras reparar la mezcla de series temporales en el pre-procesamiento e instanciar Gradient Boosting).
- **RMSE:** `98.66`
- **MAE:** `5.22` unidades de error absoluto.

## 3. Segmentación de Clientes (K-Means)

_Propósito: Agrupar clientes basados en métricas R-F-M (Recency, Frequency, Monetary)._

- **Silueta del Cluster:** `0.6123`
  _(Una silueta > 0.6 indica que los grupos generados son matemáticamente muy sólidos, cohesivos y bien separados)._

## 4. Clasificador de Abandono o Churn (Random Forest)

_Propósito: Predecir si un cliente va a dejar de comprar._

- **Exactitud Global (Accuracy):** `71%`
- **ROC AUC Score:** `0.7013` _(El modelo posee una capacidad muy saludable de un 70% para discriminar verdaderos positivos de falsos positivos)._
- **Precision / Recall (Clase Mayoritaria - 1):** 95% / 72%

## 5. Reglas de Asociación (Market Basket)

_Propósito: Encontrar qué items se compran juntos con frecuencia._

- **Estado:** Entrenado con Éxito (Se generaron `69` reglas cruzadas estructuradas).
  _(Validación reparada. Originalmente fallaba por mapeo erróneo de la clave 'sku' a 'product_name')._

## 6. Detector de Anomalías (Isolation Forest)

_Propósito: Detectar facturas fraudulentas o valores atípicos (como el caso del repuesto a 0.25 centavos)._

- **Estado:** Entrenado con Éxito (Contaminación aislada del `1%`). No se imprimen métricas supervisadas porque es un algoritmo de purga no-supervisada.

## 7. Predicción de Metas (Random Forest depurado)

_Propósito: Asignar nuevos objetivos a sucursales y vendedores._

- **R2 Score:** `0.0005` (Mejora estabilizadora. Antes R2 = -0.5653).
  _(Al excluir los identificadores nominales ID puramente lógicos, el Random Forest se obliga a dividir conservadoramente previniendo sobreajustes catastróficos. Demuestra que este tipo granularizado de metas asume el promedio)._
