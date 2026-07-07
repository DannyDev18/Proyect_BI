# ACUERDO DE CONFIDENCIALIDAD Y NO DIVULGACIÓN (NDA)

Conste por el presente documento el **Acuerdo de Confidencialidad y No Divulgación de Información** (en adelante, el "Acuerdo"), celebrado al 6 de Julio de 2026 de conformidad con las siguientes estipulaciones:

## 1. COMPONENTES Y PARTES INTERVENIENTES

- **Por una parte:** La Empresa Comercial Multisucursal (en adelante denominada como la **"Empresa"** o la **"Parte Divulgadora"**).
- **Por otra parte:** El Investigador/Desarrollador del monorepo analítico (en adelante denominado como el **"Desarrollador"** o la **"Parte Receptora"**).

Ambas partes podrán ser denominadas conjuntamente como las "Partes" e individualmente como la "Parte".

---

## 2. OBJETO DEL ACUERDO

El objeto del presente Acuerdo es resguardar la confidencialidad de toda la información comercial, técnica, financiera y personal a la que la Parte Receptora tenga acceso con motivo del diseño, desarrollo, pruebas e implementación de la **"Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal"** (proyecto de titulación académica en monorepo de contenedores Docker).

---

## 3. DEFINICIÓN DE INFORMACIÓN CONFIDENCIAL

Se considerará como **Información Confidencial** toda aquella información verbal, escrita, visual, magnética, física o digital, entregada o puesta a disposición por la Parte Divulgadora a la Parte Receptora. Específicamente, en el contexto del proyecto monorepo, incluye:

- Datos crudos o transaccionales e identificativos provenientes de la base de extracción origen SAP SQL Anywhere, tales como la tabla de clientes (`clientes_extractor.sql`) con los campos `codcli`, `ruc_cedula` y `nombre_cliente`.
- Estructura interna, diseño físico y esquemas lógicos del Data Warehouse hospedado en el contenedor PostgreSQL (`bi_postgres_edw`), en particular los esquemas `edw` (dimensiones y hechos) y `public` (tablas operacionales).
- El mapeo de correspondencia unívoca contenido en la tabla `public.cliente_lookup`, la cual mapea el `hash_anonimo` con la identidad real del cliente y su `id_cliente_transaccional`.
- El código fuente del orquestador ETL (`etl/orchestrator.py`), lógica de carga incremental (`etl/loaders/dim_loader.py`), controladores del backend en FastAPI (`backend/app/services/prediction_service.py` y `analytics_service.py`), e interfaces React en el frontend.
- Credenciales del sistema, contraseñas de las redes de contenedores Docker expuestas, configuraciones del archivo de entorno `.env` y el valor secreto de `PII_SALT`.

---

## 4. OBLIGACIONES DE LA PARTE RECEPTORA

La Parte Receptora se compromete expresamente a:

1.  **Uso Exclusivo:** Utilizar la Información Confidencial única y exclusivamente para los fines del modelado analítico, pruebas del flujo ETL y entrenamiento de los modelos de Machine Learning (tales como Apriori para cross-selling, K-Means para segmentación RFM e Isolation Forest para anomalías).
2.  **No Divulgación:** Mantener la Información Confidencial en estricto secreto. Ninguna parte de la información o sus resultados analíticos intermedios con datos reales de clientes (cédulas o nombres legibles) podrá ser compartida con terceros.
3.  **Medidas de Cuidado:** Asegurar que los repositorios de código local y archivos de configuración que contienen variables sensibles (como `PII_SALT`) no se expongan en repositorios públicos de GitHub.

---

## 5. SECCIÓN DE EXCEPCIONES

No existirá obligación de confidencialidad en los siguientes escenarios:

- Si la información pasa a ser de dominio público por causas ajenas a un incumplimiento de la Parte Receptora.
- Si la información ya era de previo conocimiento de la Parte Receptora antes de la firma.
- Si es requerida por orden de autoridad judicial o administrativa competente en virtud de una ley vigente en el Ecuador.

---

## 6. PROPIEDAD INTELECTUAL E INDUSTRIAL

La provisión de Información Confidencial bajo este Acuerdo no implica transferencia de derechos de propiedad intelectual, marcas o patentes sobre los datos originales del negocio de la Empresa. El Desarrollador retiene los derechos sobre los algoritmos generales de machine learning encapsulados en el monorepo que no utilicen datos propietarios crudos.

---

## 7. PLAZO DE CONFIDENCIALIDAD

Las obligaciones de confidencialidad se mantendrán vigentes durante un plazo de **3 años** contados a partir de la fecha de culminación y entrega de la plataforma de Business Intelligence.

---

## 8. PENALIDADES Y CONSECUENCIAS DE DISCONFORMIDAD

En caso de incumplimiento comprobado, la Parte Divulgadora estará legalmente facultada para iniciar las acciones administrativas, civiles y penales que correspondan según lo dispuesto en el Código Orgánico Integral Penal (COIP) de la República del Ecuador por delitos contra el secreto de la información y la confidencialidad de datos.

---

## 9. FIRMA DE CONFORMIDAD

Ambas partes firman al pie en dos ejemplares de igual valor técnico y legal, en la ciudad de Quito, a los 6 días de Julio de 2026.

```
__________________________________             __________________________________
Representante Legal                            Desarrollador / Investigador
Empresa Comercial Multisucursal                C.C. 1729XXXXXX
```
