# PROMPT DE IMPLEMENTACIÓN: SISTEMA DE COMISIONES VARIABLES CON DATOS REALES

---

## CONTEXTO ESTRATÉGICO

Eres un experto en implementación de sistemas de compensación variable. Vas a desarrollar un sistema completo de comisiones para una empresa comercial que opera con dos tipos de vendedores:

1. **Vendedores Externos** (territorio): visitan clientes, construyen relaciones, tienen costo de soporte más alto (vehículo, viáticos, teléfono)
2. **Vendedores Internos** (almacenes): atienden clientes que llegan al punto de venta, menor costo de soporte

**Situación Actual:**
- La empresa NO tiene un sistema formal de comisiones
- Actualmente usan una tasa plana sobre venta neta por tramos de cumplimiento
- Las facturas pueden ser a **contado** o a **crédito** (diferentes plazos: 15, 30, 45, 60, 90+ días)
- Los vendedores externos e internos comparten clientes en algunos casos (un externo presenta cotización, el cliente compra en almacén)
- Existen devoluciones, descuentos y promociones que afectan la rentabilidad
- La plataforma BI ya tiene datos de ventas, productos, clientes y vendedores

**Objetivo del Sistema:**
Implementar un sistema de comisiones que:
- Alinee los incentivos con la rentabilidad real de la empresa
- Considere el costo de financiamiento de las ventas a crédito
- Diferencie entre tipos de vendedor (externo vs interno)
- Sea transparente, configurable y con piloto en sombra
- Use **datos reales de la empresa** (no datos de prueba)

---

## REQUERIMIENTOS FUNCIONALES DETALLADOS

### 1. ESQUEMA DE COMISIONES BASE

**Principio Rector:** 
> "Se comisiona sobre lo que la empresa realmente gana (margen bruto), no sobre lo que factura, ponderado por categoría estratégica, condicionado al cumplimiento de meta y ajustado por plazo de crédito."

**La fórmula completa debe considerar cinco dimensiones:**
1. **Rentabilidad**: margen bruto de cada producto
2. **Estrategia**: categorías con tasas diferenciadas
3. **Cumplimiento**: meta mensual del vendedor
4. **Crédito**: plazo de pago otorgado al cliente
5. **Tipo de vendedor**: externo vs interno

**Fórmula Conceptual:**
La comisión final de un vendedor en un mes se calcula así:

- Primero, por cada línea de venta, se toma el margen bruto que dejó ese producto
- A ese margen se le aplica una tasa que depende de la categoría del producto (A, B, C, S o X)
- También se aplica un factor estratégico si el producto está en campaña (ejemplo: 1.3 para liquidar inventario)
- Luego se ajusta por el plazo de crédito: mientras más días a crédito, menor factor (ejemplo: contado=1.0, 15 días=0.92, 30 días=0.85, etc.)
- Se suman todas las líneas para obtener la comisión base
- Se multiplica por el factor según el tipo de vendedor (externo=1.0, interno=0.70)
- Luego se aplica el multiplicador por cumplimiento de meta (ejemplo: 100% o más=1.2, 90-99%=1.0, 80-89%=0.7, menos de 80%=0.3)
- Se restan las devoluciones del mes
- Se suman los bonos (por venta cruzada, clientes nuevos, etc.)

---

### 2. DIFERENCIACIÓN POR TIPO DE VENDEDOR

**Factor por Tipo de Vendedor:**
- **Externo (Territorio)**: factor 1.0 (base de referencia, mayor costo de soporte para la empresa)
- **Interno (Almacén)**: factor 0.70 (menor costo de soporte, menor capacidad de influir en el mix de productos)

**Cómo debe aplicarse:**
La comisión calculada por margen y categoría se multiplica por este factor. Un vendedor interno recibe el 70% de lo que recibiría un externo por la misma venta, reflejando la diferencia en estructura de costos.

**Metas Diferentes según el Tipo:**
- **Vendedor Externo**: la meta se calcula como el IQR histórico multiplicado por 1.1 (mayor potencial de venta)
- **Vendedor Interno**: la meta se calcula como el IQR histórico multiplicado por 0.95 (más realista por el tipo de atención)
- **Vendedor Nuevo**: la meta es el 60% del promedio del equipo durante los primeros 3 meses (período de adaptación y entrenamiento)

---

### 3. MATRIZ DE CATEGORÍAS Y TASAS (CON DATOS REALES)

**Metodología para Definir las Categorías con Datos Reales:**

El sistema debe analizar automáticamente los datos históricos de ventas para clasificar productos en categorías. El proceso es:

**Paso 1 - Extraer datos reales:**
Tomar todos los productos vendidos en los últimos 24 meses. Para cada producto/subclase, calcular:
- Margen bruto promedio (% sobre venta)
- Volumen total de ventas en pesos
- Número de vendedores que lo venden
- Tasa de descuento promedio otorgada

**Paso 2 - Clasificar automáticamente:**
- **Categoría A**: Productos con margen mayor a 30%, son los estratégicos que la empresa quiere empujar. Tasa sugerida: 12-15% sobre el margen.
- **Categoría B**: Productos con margen entre 15% y 30%, son el core del negocio. Tasa sugerida: 8-10% sobre el margen.
- **Categoría C**: Productos con margen menor a 15%, son commodities de alta rotación que se venden solos. Tasa sugerida: 4-6% sobre el margen.
- **Categoría S**: Servicios (instalación, garantías, consultoría). Como no tienen costo de inventario, se comisiona sobre el VALOR de la venta, no sobre el margen. Tasa sugerida: 5-8% sobre el valor.
- **Categoría X**: Excluidos (fletes, redondeos, cortesías, productos a precio 0). Tasa 0%.

**Paso 3 - Validación con datos reales:**
Antes de implementar, hacer una simulación con los últimos 12 meses de datos para ver:
- ¿Cómo impacta a cada vendedor? ¿Alguno gana mucho más o mucho menos?
- ¿Cuál es el costo total para la empresa?
- ¿Qué porcentaje del margen total se va en comisiones?

**Factor Estratégico Temporal:**
Además de la tasa base, el sistema debe permitir un multiplicador estratégico (1.0 a 1.5) que gerencia pueda activar por tiempo limitado (ejemplo: 90 días) para:
- Liquidar inventario con sobre-stock (detectado por el dashboard de bodega)
- Empujar una nueva línea de productos
- Reaccionar a campañas de la competencia

---

### 4. SISTEMA DE AJUSTE POR CRÉDITO (CON DATOS REALES)

**El Problema de las Ventas a Crédito:**
Cuando un vendedor vende a crédito, la empresa está financiando esa venta. El vendedor cobra su comisión completa, pero la empresa asume el riesgo y el costo financiero. Esto es injusto para la empresa y desalinea incentivos.

**Análisis de Plazos de Crédito Reales:**
El sistema debe analizar para cada vendedor y cada mes:
- ¿Qué porcentaje de sus ventas son a crédito?
- ¿Cuál es el plazo promedio que otorga?
- ¿Qué porcentaje de sus clientes paga tarde (después de la fecha de vencimiento)?
- ¿Qué costo financiero estimado representa para la empresa?

**Matriz de Ajuste por Plazo de Crédito (Base para Negociación):**

| Días de Crédito | Factor | % al Facturar | % al Cobrar | Racional |
|-----------------|--------|---------------|-------------|----------|
| 0 (Contado) | 1.00 | 100% | 0% | Sin riesgo, sin costo financiero |
| 1 a 15 días | 0.92 | 80% | 20% | Riesgo bajo, costo mínimo |
| 16 a 30 días | 0.85 | 70% | 30% | Riesgo moderado |
| 31 a 45 días | 0.78 | 60% | 40% | Riesgo alto |
| 46 a 60 días | 0.70 | 50% | 50% | Riesgo muy alto |
| 61 a 90 días | 0.60 | 40% | 60% | Riesgo extremo |
| Más de 90 días | 0.50 | 30% | 70% | Riesgo crítico, requiere aprobación |

**Cómo se Aplica en la Práctica:**

**Caso 1: Venta de Contado**
- El vendedor vende $10,000 en productos con margen de $3,500
- Categoría A, tasa 13% → comisión base = $3,500 × 13% = $455
- Factor crédito = 1.0 → comisión ajustada = $455 × 1.0 = $455
- Pago: 100% al facturar ($455)

**Caso 2: Venta a 30 Días**
- El vendedor vende $10,000 en productos con margen de $3,500
- Categoría A, tasa 13% → comisión base = $3,500 × 13% = $455
- Factor crédito = 0.85 → comisión ajustada = $455 × 0.85 = $386.75
- Pago: 70% al facturar ($270.73) y 30% al cobrar ($116.02)

**Caso 3: Venta a 60 Días**
- El vendedor vende $10,000 en productos con margen de $3,500
- Categoría A, tasa 13% → comisión base = $3,500 × 13% = $455
- Factor crédito = 0.70 → comisión ajustada = $455 × 0.70 = $318.50
- Pago: 50% al facturar ($159.25) y 50% al cobrar ($159.25)

**El Efecto en el Comportamiento del Vendedor:**
- Vender a contado le da $455 (100% de la comisión)
- Vender a 30 días le da $386.75 (85% de la comisión)
- Vender a 60 días le da $318.50 (70% de la comisión)

El vendedor tiene un incentivo claro a vender a mejores plazos o a ayudar a que el cliente pague rápido.

**Manejo de Pagos Reales vs. Plazo Teórico:**
El sistema debe ser inteligente. Si un cliente tiene plazo teórico de 30 días pero paga en 10 días, el vendedor debe recibir el factor correspondiente a 10 días (0.92 en lugar de 0.85). Esto se recalcula mensualmente cuando se actualiza el estado de cobro.

**Escenario de Factura Incobrable:**
Si una factura se declara incobrable (el cliente nunca pagó), el sistema debe:
- Reversión 100% de la comisión si ocurre en los primeros 90 días
- Reversión 50% si ocurre entre 90 y 180 días
- Sin reversión si ocurre después de 180 días (la empresa ya asumió la pérdida)

Esto protege a la empresa y aún así es justo para el vendedor (no se le descuenta una comisión de hace 6 meses).

---

### 5. ASIGNACIÓN DE VENTAS COMPARTIDAS (EXTERNO + INTERNO)

**El Problema:**
Un vendedor externo hace una cotización a un cliente, pero el cliente compra en el almacén atendido por un vendedor interno. ¿Quién se lleva la comisión?

**Regla de Asignación (Tres Opciones):**

**Opción A: Origen de la Venta (Recomendado)**
- Si el cliente tiene una cotización previa del externo (registrada en el sistema), el externo recibe 80% y el interno 20%
- Si el cliente llega sin cotización previa, el interno recibe 100%
- Esto incentiva al externo a registrar sus cotizaciones en el sistema

**Opción B: Mitad y Mitad**
- Siempre que un cliente con externo asignado compre en almacén, la comisión se reparte 50% - 50%
- Simple pero puede desmotivar a los internos (hacen el trabajo de cierre y reciben menos)

**Opción C: Basado en el Esfuerzo**
- El externo recibe comisión por prospección (ejemplo: $50 por cliente nuevo registrado)
- El interno recibe la comisión por la venta
- Separa los roles: el externo genera oportunidades, el interno las cierra

**Recomendación:** Implementar Opción A con un sistema de "etiquetado" donde el externo registra al cliente en el CRM. Si el cliente compra en almacén dentro de los próximos 30 días, se aplica el reparto.

---

### 6. BONOS COMPLEMENTARIOS

**Bono 1: Venta Cruzada por Asistente**
- Cuando un vendedor acepta una sugerencia del asistente de ventas (sistema de recomendaciones) y genera una venta, recibe un 5% adicional sobre el valor de esa línea
- Esto incentiva la adopción de la herramienta

**Bono 2: Cliente Nuevo o Reactivado**
- Por cada cliente que no había comprado en los últimos 6 meses y vuelve a comprar, el vendedor recibe un bono fijo de $50
- Detectable automáticamente con el análisis RFM (Recencia, Frecuencia, Monto)

**Bono 3: Cobranza Sana**
- Si el vendedor mantiene un promedio de días de cobro menor a 30 días en el mes, recibe un bono adicional del 5% sobre su comisión total
- Esto incentiva no solo vender a crédito, sino asegurarse de que se cobre rápido

**Bono 4: Cumplimiento de Visitas (Solo Externos)**
- Si el vendedor cumple con su plan de visitas mensual (ejemplo: 80% de los clientes asignados visitados), recibe un 5% adicional
- Se mide con geolocalización o registro en CRM

---

### 7. SALVAGUARDAS ANTI-ABUSO

**Salvaguarda 1: Descuentos Excesivos**
- Si un vendedor otorga un descuento mayor al 30% en una línea, esa línea NO genera comisión a menos que tenga aprobación explícita de gerencia
- El sistema detecta automáticamente y marca la línea como "pendiente de aprobación"

**Salvaguarda 2: Líneas Sin Costo en SAP**
- Si un producto no tiene costo registrado en SAP (costo = 0 o NULL), no se puede calcular margen
- En ese caso, se usa la tasa mínima (5%) sobre el VALOR de la venta (no sobre margen)
- Además, se genera un reporte automático para que gerencia corrija el costo en SAP

**Salvaguarda 3: Devoluciones**
- Las devoluciones del mes se restan de la base comisionable del vendedor en ese mismo mes
- Si un vendedor tuvo muchas devoluciones, su comisión se reduce
- La comisión nunca puede ser negativa (mínimo $0)

**Salvaguarda 4: Anulaciones**
- Solo se consideran facturas en estado "P" (pagadas/activas)
- Las facturas anuladas no generan comisión

**Salvaguarda 5: Rotación de Clientes**
- Si un vendedor tiene una tasa de rotación de clientes (churn) mayor al 30% en un trimestre, se aplica un ajuste negativo del 10% en su comisión del mes siguiente
- Esto incentiva la retención de clientes

**Salvaguarda 6: Transparencia Total**
- Cada vendedor debe ver en su dashboard EXACTAMENTE cómo se calculó su comisión:
  - Línea por línea: producto, margen, categoría, tasa, factor crédito
  - Resumen por categoría
  - Ajustes por meta
  - Bonos aplicados
  - Devoluciones descontadas
- No puede haber sorpresas. Si el vendedor entiende la fórmula, confía en el sistema.

---

### 8. PLAN DE TRABAJO PARA LA IMPLEMENTACIÓN

**Fase 1: Análisis Histórico con Datos Reales (1 semana)**

**Objetivo:** Hablar con datos, no con opiniones.

**Actividades:**
1. Analizar los últimos 24 meses de ventas para entender el perfil de margen por categoría de producto
2. Identificar qué vendedores venden qué categorías (¿quién vive de qué?)
3. Calcular la tasa de devoluciones y descuentos por vendedor
4. Analizar el comportamiento de crédito: ¿quién vende más a crédito? ¿qué plazos?
5. Generar un informe con la clasificación A/B/C/S/X propuesta basada en datos reales

**Entregable:** Presentación ejecutiva con datos concretos ("El 40% de la venta total viene de productos con margen <15%", "El vendedor X tiene 60% de sus ventas a crédito", etc.)

**Fase 2: Simulación y Diseño de la Matriz (1 semana)**

**Objetivo:** El argumento decisivo para convencer a gerencia.

**Actividades:**
1. Definir 2-3 escenarios de matriz (conservador, medio, agresivo)
2. Simular los últimos 12 meses: para cada vendedor y mes, calcular cuánto habría ganado con cada escenario
3. Calcular el costo total anual para la empresa de cada escenario
4. Calcular el porcentaje que la comisión representa sobre el margen bruto generado (KPI de sanidad)

**Entregable:** Tabla comparativa "qué habría pasado" que elimina el miedo al costo desconocido. Cada vendedor puede ver su número.

**Fase 3: Presentación y Negociación con Gerencia (1-2 sesiones)**

**Objetivo:** Obtener aprobación y definir variables finales.

**Presentación:**
1. El problema del esquema plano (con números reales)
2. El principio: comisionar sobre margen, no sobre venta
3. La matriz propuesta (basada en datos reales)
4. La simulación de costo (para eliminar el miedo)
5. Las salvaguardas (para proteger a la empresa)
6. El plan de implementación (riesgo cero con piloto en sombra)

**Preguntas a Resolver con Gerencia (llevarlas como opciones cerradas):**
- ¿Tasas finales para cada categoría? (opciones: 12/8/5, 15/10/6, etc.)
- ¿Piso para el tramo LEJOS? (0%, 30%, 50%)
- ¿Factor para vendedores internos? (0.7, 0.75, 0.8)
- ¿Bono de cobranza? (80/20, 70/30, 60/40)
- ¿Tope de descuento comisionable? (20%, 25%, 30%)
- ¿Presupuesto máximo de comisiones como % del margen? (ejemplo: 15% del margen total)

**Entregable:** Acta con variables acordadas.

**Fase 4: Piloto en Sombra (2-3 meses, Riesgo Cero)**

**Objetivo:** Probar el sistema sin afectar la nómina.

**Actividades:**
1. La plataforma calcula la comisión nueva EN PARALELO a lo que la empresa paga hoy
2. Cada vendedor ve ambos números en su dashboard ("Con el sistema nuevo habrías ganado $X")
3. No se paga nada nuevo, solo se muestra
4. Ajustar la matriz con casos reales (categorías mal clasificadas, costos faltantes en SAP)
5. Recoger feedback de vendedores (sin presión, es solo una simulación)

**Criterios de Salida del Piloto:**
- Menos del 5% de líneas sin costo en SAP
- Costo total dentro del presupuesto acordado
- Ningún vendedor pierde más del 15% vs. esquema anterior sin causa justificada
- Feedback positivo de al menos el 70% de los vendedores

**Fase 5: Implementación Técnica (después de aprobado, 1-2 semanas)**

**Cambios Técnicos Acotados:**
1. Crear tablas de configuración (matriz de categorías, multiplicadores, crédito)
2. Extender el motor de comisiones (nueva función que calcule por margen)
3. Extender el dashboard del vendedor (desglose por categoría y crédito)
4. Crear panel de configuración para gerencia (para ajustar la matriz sin programar)
5. Implementar el modo "sombra" (cálculo paralelo sin efecto)

**Rollback Garantizado:**
- El sistema actual de tasa plana queda como fallback
- Si algo sale mal, se desactiva la nueva lógica y se vuelve al sistema anterior en minutos
- No hay riesgo de perder datos o afectar la nómina

---

### 9. EJEMPLO NUMÉRICO COMPLETO PARA PRESENTACIÓN

**Escenario: Vendedor Externo con Meta de $50,000**

El vendedor logra $52,000 en ventas (104% de cumplimiento → categoría EXCELENTE, multiplicador 1.2)

**Líneas de Venta:**

| Producto | Cantidad | Valor Venta | Margen | Categoría | Tasa | Crédito |
|----------|----------|-------------|--------|-----------|------|---------|
| Commodity A | 40 uds × $25 | $1,000 | $80 (8%) | C | 5% | Contado |
| Equipo Premium | 2 uds × $500 | $1,000 | $350 (35%) | A | 13% | Contado |
| Servicio Instalación | 1 servicio | $300 | N/A | S | 6% (sobre valor) | Contado |
| Producto B | 10 uds × $200 | $2,000 | $500 (25%) | B | 9% | 30 días |

**Cálculo de Comisión Base (sin ajuste por crédito):**

- Línea 1: $80 × 5% = $4.00
- Línea 2: $350 × 13% = $45.50
- Línea 3: $300 × 6% = $18.00
- Línea 4: $500 × 9% = $45.00

**Comisión Base Total = $112.50**

**Ajuste por Crédito:**

| Línea | Comisión Base | Factor Crédito | Comisión Ajustada |
|-------|---------------|----------------|-------------------|
| Línea 1 | $4.00 | 1.0 (contado) | $4.00 |
| Línea 2 | $45.50 | 1.0 (contado) | $45.50 |
| Línea 3 | $18.00 | 1.0 (contado) | $18.00 |
| Línea 4 | $45.00 | 0.85 (30 días) | $38.25 |

**Comisión Ajustada por Crédito = $105.75**

**Factor por Tipo de Vendedor (Externo = 1.0):**
- Comisión = $105.75 × 1.0 = $105.75

**Aplicar Multiplicador por Cumplimiento (EXCELENTE = 1.2):**
- Comisión = $105.75 × 1.2 = $126.90

**Restar Devoluciones del Mes:**
- Devoluciones = $15.00
- Comisión = $126.90 - $15.00 = $111.90

**Sumar Bonos:**
- Bono cliente nuevo: $50.00
- Bono venta cruzada: $5.00
- Comisión Final = $111.90 + $55.00 = **$166.90**

**Comparación con el Sistema Actual (tasa plana 7%):**
- Venta Neta = $4,300 (suma de todas las líneas)
- Comisión Actual = $4,300 × 7% × 1.2 = $361.20

**Diferencia:** El vendedor ganaría $194.30 menos con el nuevo sistema en este ejemplo.

**PERO:** La empresa gana MUCHO más porque:
- En el sistema actual: comisión $361.20 sobre margen total de $930 = 38.8% del margen
- En el nuevo sistema: comisión $166.90 sobre margen total de $930 = 17.9% del margen

La empresa reduce el costo de comisiones de 38.8% a 17.9% del margen. **Gana la empresa, gana el vendedor más alineado, y los productos de alto margen son recompensados.**

---

### 10. PREGUNTAS CRÍTICAS PARA VALIDAR CON GERENCIA

**Pregunta 1 - Filosofía del Sistema:**
"¿Queremos incentivar VOLUMEN (vender mucho de lo que sea) o RENTABILIDAD (vender lo que deja más dinero)? El sistema actual incentiva volumen, el nuevo incentiva rentabilidad."

**Pregunta 2 - Tasas por Categoría:**
"¿Qué tan agresivos queremos ser en premiar los productos de alto margen? Opciones: conservador (10/7/4), medio (13/9/5), agresivo (15/11/6) o personalizado."

**Pregunta 3 - Impacto en Vendedores:**
"¿Estamos dispuestos a que algunos vendedores ganen menos si están vendiendo productos de bajo margen? ¿O queremos que el costo total sea neutral y solo cambiemos la distribución?"

**Pregunta 4 - Crédito:**
"¿Queremos que el crédito afecte la comisión del vendedor? Si la respuesta es NO, entonces ¿por qué el vendedor se preocuparía por el plazo de pago si la empresa financia?"

**Pregunta 5 - Piloto:**
"¿Cuánto tiempo de piloto en sombra queremos? ¿2 meses? ¿3 meses? ¿Suficiente para ver el comportamiento de los vendedores sin afectar su bolsillo?"

**Pregunta 6 - Presupuesto:**
"¿Qué porcentaje del margen bruto total queremos que se vaya en comisiones? Hoy es aproximadamente X%, ¿queremos mantenerlo, reducirlo o podemos subirlo si aumenta la rentabilidad?"

**Pregunta 7 - Vendedores Internos vs Externos:**
"¿Queremos pagar igual a internos y externos por la misma venta? Si un externo cuesta 2.5 veces más que un interno, ¿no debería ganar más comisión para compensar?"

**Pregunta 8 - Transición:**
"¿Cómo manejamos a los vendedores que salgan perdiendo en el nuevo sistema? ¿Garantía de ingreso por 3 meses? ¿Entrenamiento para que vendan mejor los productos de alto margen?"

---

### 11. MÉTRICAS DE ÉXITO DEL SISTEMA

**Métricas a Monitorear (Mensual):**

1. **Costo de Comisiones**: % del margen bruto que se paga en comisiones (objetivo: 15-20%)
2. **Mix de Productos**: % de ventas de categoría A vs C (objetivo: aumentar categoría A en 5% anual)
3. **Plazo de Crédito Promedio**: días promedio de cobro (objetivo: reducir en 10% en 6 meses)
4. **Tasa de Devoluciones**: % de ventas devueltas (objetivo: mantener o reducir)
5. **Rotación de Vendedores**: % de vendedores que renuncian (objetivo: mantener o reducir)
6. **Satisfacción de Vendedores**: encuesta trimestral (objetivo: >80% de satisfacción)
7. **Adopción del Sistema**: % de vendedores que revisan su dashboard semanalmente (objetivo: >70%)

**Métricas a Monitorear (Trimestral):**

1. **Margen Bruto Total**: crecimiento vs. trimestre anterior (objetivo: crecimiento positivo)
2. **Rentabilidad por Vendedor**: margen generado vs. costo de comisiones (objetivo: mejora continua)
3. **Rotación de Clientes**: % de clientes que dejan de comprar (objetivo: reducción)
4. **Venta Cruzada**: % de ventas generadas por recomendaciones del asistente (objetivo: crecimiento)

**Métricas a Monitorear (Anual):**

1. **ROI del Sistema de Comisiones**: ¿La empresa gana más en margen de lo que paga en comisiones?
2. **Evolución del Mix**: ¿Ha cambiado la composición de ventas hacia productos de mayor margen?
3. **Cumplimiento de Metas**: ¿Más vendedores alcanzan la meta? ¿O la meta es más realista?

---

### 12. PLAN DE COMUNICACIÓN CON VENDEDORES

**Antes de la Implementación:**
1. **Reunión General**: Explicar el POR QUÉ del cambio (la empresa no puede seguir pagando igual por productos de diferente rentabilidad)
2. **Simulación Personalizada**: Cada vendedor recibe su simulación de 12 meses con el nuevo sistema
3. **Preguntas y Respuestas**: Sesión abierta para resolver dudas
4. **Grupo de Prueba**: Voluntarios que prueban el sistema primero y dan feedback

**Durante el Piloto en Sombra:**
1. **Dashboard Dual**: El vendedor ve "Lo que ganaste hoy" y "Lo que habrías ganado con el nuevo sistema"
2. **Semanas de Feedback**: Sesiones semanales para recoger impresiones
3. **Ajustes Rápidos**: Si algo no tiene sentido, se ajusta rápidamente

**Después de la Implementación:**
1. **Entrenamiento Continuo**: Cómo mejorar la comisión (vender categoría A, cobrar rápido, etc.)
2. **Rankings Mensuales**: Top vendedores por categoría (no solo por volumen)
3. **Reconocimiento**: Premios especiales para los que mejor se adaptan

**Mensajes Clave para Vendedores:**
1. "Este sistema te paga por lo que realmente aportas a la empresa"
2. "Puedes ganar más si vendes productos de alto margen, no solo volumen"
3. "Tienes control sobre tu comisión: tú decides qué vender y a qué plazo"
4. "Es transparente: ves exactamente cómo se calcula cada peso"
5. "Es justo: los productos difíciles pagan más, los fáciles pagan menos"

---

### 13. CONCLUSIÓN Y RECOMENDACIÓN FINAL

**El sistema propuesto es:**

✅ **Justo**: Comisiona sobre el margen, no sobre el volumen. Cada producto paga según su contribución real.

✅ **Alineado**: Incentiva lo que la empresa quiere: productos de alto margen, cobros rápidos, clientes rentables.

✅ **Transparente**: El vendedor ve exactamente cómo se calcula cada peso. No hay sorpresas.

✅ **Configurable**: Gerencia ajusta tasas y factores sin programar. Se adapta a cambios de estrategia.

✅ **Seguro**: Piloto en sombra, rollback garantizado, salvaguardas anti-abuso.

✅ **Equilibrado**: Reconoce la diferencia entre vendedores externos e internos.

✅ **Basado en Datos**: Usa datos reales de la empresa, no suposiciones.

**Lo que NO es:**
- No es un sistema para bajar comisiones (puede subirlas si se vende bien)
- No es un sistema complicado para el vendedor (solo ve el resultado final)
- No es un sistema rígido (se ajusta con la estrategia de la empresa)

**Recomendación Final:**
Implementar este sistema es una decisión estratégica que transforma la fuerza de ventas de "vendedores de volumen" a "vendedores de rentabilidad". La empresa gana en margen, los vendedores ganan en claridad y motivación, y los clientes ganan porque los vendedores se enfocan en darles el producto adecuado, no el que más comisión da.

El piloto en sombra garantiza que la transición sea suave y sin riesgos. Si después de 3 meses no funciona, se desactiva y se vuelve al sistema anterior. No hay pérdida de tiempo ni de dinero.

**La pregunta final para gerencia es:** "¿Queremos seguir pagando igual por productos que dejan diferente rentabilidad, o queremos un sistema que premie el verdadero valor que cada vendedor aporta a la empresa?"

---

### 14. GLOSARIO DE TÉRMINOS

**Margen Bruto**: Diferencia entre el precio de venta y el costo del producto. Ejemplo: vendo a $100, me costó $70 → margen $30 (30%).

**Tasa Plana**: El sistema actual donde todos los productos pagan el mismo porcentaje (ejemplo: 7% sobre la venta neta).

**Categoría A/B/C/S/X**: Clasificación de productos según su margen y estrategia comercial.

**Factor Estratégico**: Multiplicador temporal (1.0 a 1.5) para empujar productos específicos.

**Factor Crédito**: Reducción de la comisión según el plazo de pago otorgado al cliente.

**Multiplicador por Cumplimiento**: Ajuste de la comisión según qué tan cerca estuvo el vendedor de su meta mensual.

**Piloto en Sombra**: Cálculo en paralelo del nuevo sistema sin afectar la nómina actual.

**Salvaguarda**: Regla de protección para evitar abusos (descuentos excesivos, devoluciones, etc.).

**Rollback**: Capacidad de volver al sistema anterior si algo sale mal.

**EDW**: Data Warehouse de la empresa donde están todos los datos históricos.