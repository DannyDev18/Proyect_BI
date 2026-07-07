---
description: Entrenar, evaluar y serializar modelos de Machine Learning (Predicción de Ventas)
---

Sigue este procedimiento para ejecutar y validar los modelos predictivos de Machine Learning del proyecto (conforme a `docs/hoja_de_ruta_ejecucion.md` y la implementación actual en `backend/app/services/ventas_service.py`):

### 🧠 Estado del Modelo Predictivo en el Proyecto

1. **Entrenamiento en Tiempo Real (Actual):**
   Actualmente, el backend de FastAPI en `ventas_service.py` realiza un entrenamiento dinámico **en memoria (on-the-fly)** cada vez que se requiere una predicción. El servicio lee los datos agregados mensuales de `edw.fact_ventas_detalle`, los convierte en un DataFrame de pandas y entrena un regresor **Random Forest (scikit-learn)** combinándolo con un ajuste de tendencia de **Regresión Lineal** para la explicación descriptiva.
2. **Entrenamiento Desacoplado (Fase 3 del Plan de Ejecución):**
   Si se planea persistir el modelo entrenado y serializado en disco (`.joblib`) para optimizar el tiempo de respuesta, se estructurará un pipeline independiente bajo el directorio `ml/`.

---

### Opción A: Probar e Invocar el Entrenamiento Dinámico (FastAPI Backend)

Ejecuta los siguientes pasos para levantar la API localmente y forzar el entrenamiento del modelo del módulo de ventas:

1. **Preparar el Entorno del Backend**
   Navega a la carpeta de backend y asegúrate de tener las dependencias de ciencia de datos instaladas (como `scikit-learn`, `pandas`, `numpy` listadas en `backend/requirements.txt`):
   `cd c:\Tesis\backend`
   `python -m venv venv`
   - En Windows (PowerShell):
     `venv\Scripts\Activate.ps1`
   - En Linux/macOS:
     `source venv/bin/activate`
     `pip install -r requirements.txt`

2. **Ejecutar el Servidor de Desarrollo**
   Inicia la API FastAPI local usando uvicorn:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

3. **Invocación del Endpoint Predictivo (Entrenamiento e Inferencia)**
   Realiza una petición HTTP en otra terminal para disparar la extracción del EDW, el ajuste del estimador RandomForest y la predicción:
   - **Predicción Global:**
     `curl "http://localhost:8000/api/v1/ventas/prediccion"`
   - **Predicción con Filtro por Sucursal/Categoría:**
     `curl "http://localhost:8000/api/v1/ventas/prediccion?sucursal=Quito%20Norte&categoria=Computadoras"`
     _La respuesta JSON retornará el R² score (`r2_score`), el método ("Random Forest (scikit-learn)"), la explicación del ajuste de tendencia y la serie histórica junto a la proyección._

---

### Opción B: Implementar y Ejecutar el Script de Entrenamiento Desacoplado (Fase 3)

Para entrenar TODOS los modelos (Ventas, Demanda, Metas, Churn, Análisis RFM y Anomalías) de forma unificada desde el Data Warehouse:

1. **Crear Estructura e Instalar Dependencias**
   Asegúrate de estar en el entorno de `ml` e instalar los requerimientos.

2. **Ejecutar el Orquestador Unificado**
   Toda la lógica de extracción y entrenamiento de Machine Learning ha sido centralizada. Solo necesitas ejecutar un único archivo para entrenar la suite completa:

   ```bash
   cd c:\Tesis\ml
   python main.py
   ```

   El orquestador registrará el avance y automáticamente depositará los binarios `.pkl` en `ml/models/`.

3. **Publicar Modelos en el Backend**
   Una vez entrenados, recarga el montaje Dockerizado para que la API de FastAPI reaccione a los modelos mejorados:
   ```bash
   python publish_models.py
   ```
