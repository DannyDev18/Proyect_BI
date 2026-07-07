# PROTOCOLO DE ANONIMIZACIÓN Y SEUDONIMIZACIÓN DE DATOS (ANEXO TÉCNICO-LEGAL LOPDP)

Este documento constituye el **Anexo Técnico** que detalla los mecanismos criptográficos y arquitectónicos implementados para dar estricto cumplimiento al principio de seguridad y confidencialidad exigido por la **Ley Orgánica de Protección de Datos Personales (LOPDP)** del Ecuador en la plataforma analítica.

---

## 1. PRINCIPIO DE ARQUITECTURA: PRIVACIDAD DESDE EL DISEÑO

La plataforma de Business Intelligence e Inferencia predictiva implementa el concepto de **Privacidad desde el Diseño (Privacy by Design)**. Se establece que el almacenamiento en el Data Warehouse (esquema `edw`) no requiere, ni debe contener, datos de carácter personal (DCP) legibles en texto claro de clientes o empleados. Toda la lógica analítica ocurre sobre identificadores indirectos (seudónimos).

En el archivo `edw/02_dimensiones.sql` se eliminaron físicamente las columnas que exponían PII en el pasado: `codcli`, `ruc_cedula`, y `nombre_cliente` de la tabla `edw.Dim_Cliente`.

---

## 2. MECANISMO DE SEUDONIMIZACIÓN CRIPTOGRÁFICA

Para transformar los datos identificativos (Cédula/RUC, Nombre de Clientes) se utiliza un algoritmo hash criptográfico **HMAC con SHA-256** acoplado a una clave `PII_SALT` externa y de alta entropía.

### Algoritmo de Hashing:

La fórmula matemática aplicada en Python y ejecutada durante las transformaciones del pipeline ETL es:

$$\text{Cliente seudónimo} = \text{HMAC-SHA256}(\text{Clave PII\_SALT Criptográfica}, \text{codcli})$$

### Características técnicas del método:

1.  **Unidireccionalidad:** El SHA-256 no es un método de cifrado reversible (no posee una clave de descifrado). Es matemáticamente inviable revertir el hash final obtenido para recuperar la cédula o nombre original.
2.  **Mitigación de Ataques por Fuerza Bruta (Rainbow Tables):** El uso de la firma HMAC junto a la clave `PII_SALT` de entorno seguras en `.env` imposibilita que un atacante externo, en caso de acceder de forma no autorizada al Data Warehouse, pueda descifrar las identidades de los clientes cruzando los hashes con listas públicas de cédulas chilenas o ecuatorianas.
3.  **Preservación de Relaciones Analíticas:** Como el algoritmo es determinista, a una misma identificación de cliente siempre le corresponderá el mismo hash de 64 caracteres. Esto permite al DW mantener la integridad referencial y las relaciones con las tablas de hechos de ventas de manera transparente.

---

## 3. FLUJO OPERACIONAL DEL ETL PARA SEUDONIMIZAR CLIENTES

Al procesar la dimensión de Clientes, el orquestador ETL (`etl/orchestrator.py`) realiza la siguiente intercepción:

```
  [SAP SQL Anywhere] ──(Datos DCP Orgánicos)──> [Procesador ETL en Python]
                                                        │
                            Seudonimiza con HMAC-SHA256 │ (Utilizando PII_SALT)
                                                        ▼
  [public.cliente_lookup] <─────── [Distribuye Datos] ───────> [edw.dim_cliente]
  (Mapeo Hash-Identidad real)                                 (Solo Hashes y datos
                                                               de comportamiento)
```

1.  **Aislamiento en Mapeo:** El nombre real y dirección se direccionan únicamente hacia la tabla oculta y segura `public.cliente_lookup` en la base operativa, cuyo acceso de selección está denegado a analistas o perfiles sin privilegios de descargo.
2.  **Carga Analítica Blindada:** Hacia la dimensión `edw.dim_cliente` se inyecta única y exclusivamente el `hash_anonimo` como llave de negocio, junto a datos cuantitativos agregados (ciudad, volumen de compra, sucursal recurrente) libres de datos personales identificables.

---

## 4. ANÁLISIS DE APRENDIZAJE AUTOMÁTICO (MLOPS) ANÓNIMO

El entorno productivo de machine learning está diseñado para ignorar la identidad biográfica de los sujetos evaluados:

- **Modelado de Churn (Abandono):** La predicción se realiza utilizando como vector de entrada variables numéricas: frecuencia de compra, días de inactividad fiscal y el `hash_anonimo`. El modelo `churn_classifier.pkl` no conoce nombres de pila ni cédulas.
- **Recomendación de Productos (Apriori):** Las reglas de asociación analizan transacciones de venta asociadas estrictamente a identificaciones hashed en la tabla `fact_ventas_detail`. El archivo de reglas exportado `.joblib` es un conjunto de combinaciones numéricas de códigos de artículo no propenso a fugas legales de PII.
- **Seguridad para Ciencia de Datos (EDA):** A los científicos de datos autorizados se les provee una vista segura y controlada llamada `ml.v_ventas_cruzadas_desanonima` (creada mediante un join relacional contra `public.cliente_lookup`), de manera que puedan ver el comportamiento del modelo e interpretar el impacto predictivo de la retención sin necesidad de exportar datos biográficos del servidor de base de datos principal.

---

## 5. CONTROL DE ACCESO PARA LA RE-IDENTIFICACIÓN (DE-ANONYMIZATION)

La re-identificación controlada en el frontend (necesaria para que el gerente sepa a qué cliente contactar para evitar el Churn) es de-anonimizada por el backend en FastAPI de manera dinámica a nivel de memoria RAM:

1.  API recibe consulta con Token JWT válido.
2.  Inyección de permisos valida si el rol del usuario posee permisos específicos (`gerencia` o `administrador`).
3.  FastAPI realiza un `JOIN` dinámico de alta velocidad contra la tabla aislada `public.cliente_lookup`.
4.  La información hidratada en JSON se transmite encriptada por HTTPS canalizado hacia la SPA de React del Gerente autorizado.

Este protocolo técnico e institucional asegura que la organización mantenga los más rigurosos estándares de cumplimiento legal de seguridad exigidos por la LOPDP en el Ecuador.
