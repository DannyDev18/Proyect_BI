# Contratos ML — guía de uso

- **Fecha:** 2026-07-09
- **Alcance:** `ml/src/contracts/` (infraestructura), `ml/contracts/models/*.json` (los 7 contratos declarativos), `ml/tests/test_model_contract.py`.
- **Origen:** implementa la Fase 1 especificada en [docs/auditoria/12_fase0_analisis_capa_contratos_ml.md](auditoria/12_fase0_analisis_capa_contratos_ml.md) §5–6, sobre los hallazgos de [docs/auditoria/11_auditoria_tecnica_modelos_ml.md](auditoria/11_auditoria_tecnica_modelos_ml.md).
- **Estado:** infraestructura activa; los 7 contratos nacen en `status: "draft"`. Ningún `.pkl` fue modificado ni reentrenado en esta fase.

---

## 1. Propósito

Antes de esta capa, un modelo se publicaba (`.pkl` copiado al volumen que monta el backend) y los errores de contrato entre entrenamiento y serving se descubrían — o no — como `0.0` / `"Error"` degradado en el dashboard (auditoría 11: 6 de 7 modelos rotos en producción sin que nada lo señalara).

La capa de contratos invierte ese flujo: **un modelo no se publica si no pasa la validación de su contrato.**

```
Contrato JSON (declarativo, escrito ANTES de entrenar)
   ↓
Entrenamiento del modelo que debe CUMPLIR el contrato
   ↓
Validación automática (contract_validator.py)  ← barrera de calidad
   ↓
Exportación (save_artifact extendido: pkl + meta.json completo)
   ↓
publish_models.py (solo si el contrato ACTIVE pasó)
```

**Regla D-2 (no negociable):** un contrato se redacta desde el diseño esperado del pipeline y las reglas de negocio del EDW — nunca se deriva de un `.pkl` existente, de `feature_names_in_`, ni del comportamiento actual del serving. Los 7 `.pkl` en `ml/models/` son artefactos **legacy**: sirven de referencia histórica/diagnóstico, nunca de fuente para un contrato.

---

## 2. Componentes

| Archivo | Contenido |
|---|---|
| `ml/src/contracts/feature_schema.py` | `FeatureSpec` (una columna: nombre, dtype, obligatoriedad, nulos) y `FeatureSchema` (conjunto ordenado de columnas) con `.diff()` contra columnas reales |
| `ml/src/contracts/model_contract.py` | `ModelContract` (nombre, versión, `task`, `status`, `features`, `target`, `output`, `population_filter`, `library_versions`, `data_range`, `known_serving_mismatch`, `notes`) + carga/guardado JSON |
| `ml/src/contracts/artifact_schema.py` | `ArtifactMetadata`: esquema del `.meta.json` extendido (superset retrocompatible del formato legacy) |
| `ml/src/contracts/contract_validator.py` | `validate_features()`, `validate_artifact()`, `validate_prediction()` + `run_report()` (modo CLI/gate) |
| `ml/contracts/models/*.json` | Los 7 contratos declarativos (sales, demand, segmentation, churn, anomalies, recommendation, goals), todos `status: "draft"` |
| `ml/tests/test_model_contract.py` | Smoke test paramétrico sobre los 7 contratos; artefactos legacy marcados `xfail` con referencia al hallazgo de la auditoría 11 |
| `ml/src/utils/model_export.py` | `save_artifact()` extendido con parámetros opcionales (`contract_name`, `contract_version`, `library_versions_used`, `data_range`, `population_filter`, `target_transform`) + helper `library_versions()` |

---

## 3. Anatomía de un contrato

```json
{
  "name": "sales",
  "version": "0.1.0",
  "task": "regression",
  "status": "draft",
  "features": [
    {"name": "lag_7_y_sales_net", "dtype": "float", "required": true, "nullable": false, "description": "..."}
  ],
  "target": {
    "name": "y_sales_net",
    "transform": "log1p",
    "inverse_transform": "expm1",
    "description": "..."
  },
  "output": {"type": "float", "unit": "USD", "plausible_range": [0, 5000000]},
  "population_filter": {"description": "...", "sql_condition": "..."},
  "library_versions": {},
  "data_range": {},
  "known_serving_mismatch": ["H-01: ..."],
  "notes": "..."
}
```

- **`task`** ∈ `{regression, classification, clustering, recommendation, anomaly_detection}`.
- **`status`** ∈ `{draft, active}`. `draft` no bloquea nada (solo informa). `active` es un **gate obligatorio**: si el artefacto correspondiente no cumple, `contract_validator.run_report()` devuelve `False` (exit code 1).
- **`target.transform`/`inverse_transform`**: existen específicamente para que un artefacto como el de ventas/demanda sea autocontenido (p.ej. `sklearn.compose.TransformedTargetRegressor`) y `predict()` devuelva unidades reales, no el espacio `log1p` — es la corrección estructural de H-01.
- **`output.plausible_range`**: rango de negocio plausible de la predicción. Es lo que convierte un bug de escala silencioso ("venta diaria de 12.3 USD") en un fallo de contrato explícito vía `validate_prediction()`.
- **`population_filter`**: describe el filtro de estado/devolución que entrenamiento y serving DEBEN compartir (cierra H-15 por diseño). Con el nuevo EDW, se resuelve vía `JOIN dim_estado_documento` (cambio C-1, doc 12 §3).
- **`known_serving_mismatch`**: lista de hallazgos de la auditoría 11/12 que documentan por qué el `.pkl` legacy no cumple el contrato — no se "arreglan" en Fase 1, solo se referencian.

---

## 4. Cómo registrar/actualizar un contrato

1. Editar (o crear) el JSON en `ml/contracts/models/<nombre>.json`. El `name` debe coincidir con el nombre de artefacto que usará `contract_validator` (`<name>.pkl` / `<name>.meta.json` en `ML_MODELS_DIR`).
2. Mientras el dataset/features del modelo nuevo no estén definidos, dejar `"features": []` y documentar el diseño esperado en `notes` — **no copiar `feature_names_in_` de un `.pkl` legacy** (violaría D-2).
3. Cuando el modelo se reconstruya sobre el EDW nuevo (Fase 2/3) y su dataset esté fijado, completar `features`, `population_filter.sql_condition`, `data_range` y pasar `status` a `"active"`.
4. Correr `ml/tests/test_model_contract.py`: la primera vez que un modelo se reconstruye, quitar su entrada de `LEGACY_XFAIL_REASON` para que el test pase en modo estricto.

## 5. Cómo validar antes de publicar

Desde `ml/`:

```bash
python -m src.contracts.contract_validator
```

Imprime el estado de los 7 contratos y sale con código 1 si algún contrato `active` falla. Debe ejecutarse **antes** de `publish_models.py` (que reinicia el backend con los `.pkl` nuevos) — nunca se importa código de `backend/` desde aquí (los contratos son la única interfaz declarada entre ambos lados, no hay acoplamiento de paquetes Python entre las dos imágenes Docker).

Para pruebas unitarias/CI:

```bash
pytest ml/tests/test_model_contract.py -v
```

## 6. Cómo emitir metadata completa desde el entrenamiento

`save_artifact()` (en `ml/src/utils/model_export.py`) acepta ahora, además de los parámetros legacy (`algorithm`, `features`, `metrics`, `extra`), estos parámetros opcionales — omitirlos preserva el comportamiento anterior exacto:

```python
from src.utils.model_export import save_artifact, library_versions

save_artifact(
    modelo_entrenado,
    "sales.pkl",
    algorithm="RandomForestRegressor",
    features=contract.features.names,
    metrics=metricas_reales,          # cierra H-18/H-09: el sidecar deja de tener metrics: {}
    contract_name="sales",
    contract_version="0.1.0",
    library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
    data_range={"desde": "2023-07-01", "hasta": "2026-07-01"},
    population_filter="estado_documento = 'Procesada' AND NOT es_devolucion",
    target_transform="log1p",
)
```

## 7. Cómo evitar la divergencia entrenamiento/serving

- El contrato es la **única** fuente de verdad de columnas de entrada — ni `feature_names_in_` del estimador (no universal: CatBoost no lo expone, H-07) ni la copia manual en `backend/app/ml/preprocessing.py` deben considerarse autoritativas.
- Cuando se reescriban `ml/src/data/make_dataset.py` y los repositorios del backend (`dataset_repository.py`, `prediction_repository.py`) en la Fase 2, ambos deben construir las columnas exactamente en el orden y con los nombres declarados en `contract.features` — es lo que un futuro test de integración (Fase 3+) podrá verificar automáticamente comparando ambos lados contra el mismo JSON.
- Ningún `.pkl` se considera "oficial" hasta que su contrato esté `active` y `contract_validator.run_report()` pase.

## 8. Flujo de desarrollo resumido

1. Diseñar/actualizar el contrato (`draft`) a partir de las reglas de negocio y el EDW actual — nunca desde el `.pkl` legacy.
2. Reescribir la extracción del dataset (`make_dataset.py` / vistas `ml.*`) para que produzca exactamente las columnas del contrato.
3. Entrenar con `model_selector.py` (reutilizable) y exportar con `save_artifact()` pasando la metadata de Fase 1.
4. Correr `contract_validator.run_report()`; si pasa, promover el contrato a `active`.
5. Quitar el `xfail` correspondiente en `ml/tests/test_model_contract.py`.
6. Recién entonces, `publish_models.py`.

Ver el detalle modelo por modelo (dataset origen, features críticas, cambios por EDW, validaciones necesarias) en [docs/auditoria/12_fase0_analisis_capa_contratos_ml.md](auditoria/12_fase0_analisis_capa_contratos_ml.md) §6, Fase 3.
