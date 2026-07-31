# Prompt — Presentación ejecutiva para gerencia: Módulo de Metas y Comisiones Variables

> **Propósito de este archivo:** no es un manual ni documentación técnica. Es el **prompt** que se
> entrega a un generador de diapositivas (Claude, GPT, Gamma, Copilot en PowerPoint, etc.) para
> producir la presentación con la que se solicita a gerencia la **aprobación de puesta en
> producción** del esquema de Comisiones Variables.
>
> **Por qué existe:** el proyecto ya tiene manuales completos
> (`docs/manual_metas_y_comisiones.md`, 404 líneas) y auditorías de datos
> (`docs/auditoria/30_comisiones_variables.md`), pero ambos están escritos para *operar* y
> *desarrollar* el módulo — ninguno sirve para **vender la decisión** a un comité gerencial que no
> va a leer 400 líneas ni entiende de `codalm` ni de IQR.
>
> **Cómo usarlo:** copiar el bloque `## PROMPT` completo (desde "Eres un consultor…" hasta el final)
> y pegarlo en la herramienta de generación. Todo el material fáctico necesario va incluido en el
> propio prompt (§DATOS REALES), para que el generador **no tenga que inventar ni una cifra**.

---

## PROMPT

Eres un consultor senior en compensación variable y comunicación ejecutiva. Vas a producir una
**presentación de decisión** (no una capacitación, no una demo técnica) dirigida al comité gerencial
de una empresa comercial ecuatoriana de repuestos y baterías automotrices, con 7 sucursales y ~11
vendedores activos.

**El objetivo único de la presentación es obtener una firma:** que gerencia apruebe activar el
esquema de **Comisiones Variables** en producción, comenzando por un piloto en modo sombra de 2 a 3
meses. Todo lo demás (explicar pantallas, describir la fórmula) existe solo en función de ganar esa
aprobación. Si una diapositiva no ayuda a conseguir la firma, no va.

### Reglas absolutas (no negociables)

1. **Cero cifras inventadas.** Usa exclusivamente los datos del bloque §DATOS REALES. Están
   extraídos del Data Warehouse real de la empresa (521.766 líneas de venta). Si necesitas un número
   que no está ahí, escribe explícitamente `[PENDIENTE DE MEDIR]` en la diapositiva en vez de
   estimarlo. Un número inventado que gerencia detecte destruye la credibilidad de toda la
   propuesta.
2. **Honestidad sobre las limitaciones.** La presentación debe incluir una sección propia de
   contras y brechas de datos (§DIAPOSITIVAS, slide 18-19). No la escondas ni la suavices: un comité
   gerencial que descubre después una limitación no declarada asume que hubo otras ocultas. La
   transparencia sobre lo que el sistema *no* puede hacer es el argumento más fuerte a favor de lo
   que *sí* puede.
3. **Vocabulario de negocio, no de ingeniería.** Prohibido en el cuerpo de las diapositivas:
   `endpoint`, `payload`, `IQR`, `SQL`, `Pydantic`, `React`, `codven`, `commit`. Traduce:
   "IQR" → "recorte estadístico de meses atípicos"; "endpoint" → "pantalla" o "consulta";
   "modo sombra" → "piloto en paralelo, sin afectar el pago". Los nombres técnicos solo pueden
   aparecer en las notas del orador o en un anexo.
4. **Cada afirmación de beneficio debe estar anclada** a un dato de §DATOS REALES o marcada
   explícitamente como hipótesis a validar en el piloto. No uses "aumenta la rentabilidad un X%"
   sin respaldo.
5. **El foco es el esquema variable** (comisión sobre margen por categoría/crédito/tipo de
   vendedor). El esquema de metas automáticas y el esquema plano de comisión ya están en
   producción y funcionando — se presentan solo como el punto de partida contra el cual se compara,
   no como el protagonista.

### Formato de salida

- **22 a 26 diapositivas**, en español.
- Para cada diapositiva entrega: **(a)** título, **(b)** el contenido visible (bullets cortos,
  máximo 6 por slide, máximo ~14 palabras por bullet), **(c)** descripción del visual sugerido
  (gráfico, tabla, diagrama, captura de pantalla a tomar), **(d)** notas del orador con el guion
  hablado (2-4 frases, aquí sí puede haber detalle técnico), **(e)** el tiempo objetivo en minutos.
- Duración total del bloque hablado: **20 minutos**, dejando 10 para preguntas.
- Al final, produce además: un **resumen ejecutivo de una página** (para dejar impreso sobre la
  mesa) y una **lista de 10 preguntas difíciles previsibles con su respuesta preparada** — ver
  §ENTREGABLES ADICIONALES.

### Tono

Directo, cuantitativo, sin lenguaje de marketing. El comité es dueño/gerencia de una empresa
familiar-profesionalizada: valora el control, la reversibilidad y no pagar de más; desconfía de
sistemas que "deciden solos" y de consultores que prometen porcentajes. Habla de **dinero, riesgo y
control**, en ese orden. Nunca digas "inteligencia artificial" para describir un cálculo
determinista: el motor de comisiones es aritmética auditable, no un modelo predictivo, y presentarlo
como IA sería mentir sobre lo que hace (el módulo de metas sí usa estadística y un detector de
anomalías, y eso sí se puede nombrar como tal).

---

## DIAPOSITIVAS — estructura obligatoria

Sigue este arco narrativo. Puedes ajustar el reparto de slides dentro de cada bloque, pero no
eliminar bloques ni reordenarlos.

### Bloque 1 — El problema (slides 1-4, 3 min)

1. **Portada.** Título orientado a la decisión, no al sistema: algo como "Comisionar sobre lo que la
   empresa gana — Propuesta de aprobación de piloto". Fecha, presentador.
2. **La pregunta que resuelve esta reunión.** Una sola pregunta en pantalla grande:
   *"¿Estamos pagando comisión sobre venta o sobre utilidad?"* Hoy la respuesta es: sobre venta.
3. **El problema del esquema actual, en números reales.** El esquema plano paga un % sobre Venta
   Neta por tramos de cumplimiento. Consecuencia: dos ventas del mismo monto pagan la misma
   comisión aunque una deje 27% de margen y la otra 0,27%. Usa el contraste real de categorías:
   `HER` (herramientas, 27,44% de margen) vs. `ALF` (alfombras, **0,27%**) vs. `LLAN` (llantas
   Hankook, 2,96%). Visual: barras de margen % por categoría, resaltando esas tres.
4. **El costo oculto del crédito.** El 38,4% de las líneas de venta se facturan a 30 días: la
   empresa financia esa venta, asume el riesgo de cobro, y hoy paga la misma comisión que si fuera
   de contado. Visual: dona 61,6% contado / 38,4% crédito 30 días.

### Bloque 2 — La propuesta (slides 5-8, 4 min)

5. **El principio en una frase.** "Se comisiona sobre el margen bruto real de cada producto vendido,
   ponderado por categoría estratégica, ajustado por el plazo de crédito otorgado y por el tipo de
   vendedor." Nada más en la slide.
6. **La fórmula, en lenguaje de negocio.** Diagrama de flujo horizontal de 6 pasos, sin notación
   matemática:
   margen de la línea → × tasa de su categoría (A/B/C/S/X) → × factor de campaña →
   × factor por plazo de crédito → suma de todas las líneas → × factor tipo de vendedor →
   × multiplicador por cumplimiento de meta → − devoluciones → + bonos → **piso $0, nunca
   negativa**.
   Enfatiza el piso: la comisión nunca puede salir negativa por más que haya devoluciones.
7. **Las 5 categorías y sus tasas.** Tabla A/B/C/S/X con criterio, tasa y ejemplo real de
   categoría (ver §DATOS REALES, tabla de matriz). Explica en una línea por qué comisionar sobre
   margen es **auto-limitante**: si el margen de una categoría es 0,27%, la comisión resultante es
   trivial por construcción — el sistema no puede pagar más de lo que la empresa ganó.
8. **Externo vs. interno.** Factor 1,0 vs. 0,70, y metas diferenciadas (×1,10 vs. ×0,95). Explica
   el razonamiento de negocio: el vendedor externo tiene mayor costo de soporte (vehículo,
   viáticos) y mayor capacidad de influir en el mix de productos; el interno atiende demanda que ya
   llegó al local. Menciona la regla de vendedor nuevo (60% del promedio del equipo los primeros 3
   meses) como señal de que el sistema no castiga a quien recién entra.

### Bloque 3 — Cómo lo vive el gerente (slides 9-13, 5 min)

Esta es la sección que el comité más va a escrutar: quieren saber **qué botones controlan ellos**.
Una slide por pantalla, con captura de pantalla real y las acciones que habilita. Deja marcado
`[CAPTURA: <ruta>]` donde deba insertarse el pantallazo.

9. **Panorama: una sola pantalla, tres pestañas.** `Metas y Comisiones` (menú Gerencia) →
   pestañas *Operación*, *Comisiones Variables · Config*, *Comisiones Variables · Simulación*.
   Visual: diagrama de las 3 pestañas con una frase de propósito cada una.
   `[CAPTURA: /gerencia/metas — barra de pestañas]`
10. **Pestaña Operación — Consola de Metas.** Qué controla gerencia aquí: el período de
    planificación, el **Factor de Presión Comercial** (deslizador 0-25% que empuja todas las metas
    al alza), el botón que genera el plan del mes para todos los vendedores, la edición manual del
    monto y del % de comisión de cada vendedor fila por fila, y **Aprobar / Rechazar** por vendedor.
    Punto clave para el comité: **ninguna meta entra en vigor sin aprobación humana explícita**.
    `[CAPTURA: GoalsConsole]`
11. **Pestaña Operación — Transparencia del cálculo.** El botón "Info" junto a cada vendedor abre el
    detalle de **por qué salió ese número**: cuántos meses de historial se usaron, cuántos meses
    atípicos se recortaron, el componente estacional (qué vendió en el mismo mes de años
    anteriores), la tendencia de los últimos 4 meses y qué tan errático es ese vendedor. Argumento:
    esto es lo que convierte la meta de "cifra impuesta" en "cifra explicable" frente al vendedor.
    `[CAPTURA: drawer "Cómo se calculó la meta sugerida"]`
12. **Pestaña Config — la palanca de política comercial.** Cuatro sub-pestañas:
    - *Matriz de categorías*: por cada una de las 22 categorías reales del catálogo, su grupo
      (A/B/C/S/X), su tasa, si se comisiona sobre margen o sobre valor, y un **factor estratégico**
      temporal (0,5×-1,5×) para empujar una categoría puntual — ej. liquidar sobre-stock detectado
      por el módulo de Bodega. Cada cambio abre una vigencia nueva: **nunca se reescribe la
      historia**.
    - *Factores de crédito*: cuánto se reduce la comisión por tramo de plazo.
    - *Tipo de vendedor*: externo/interno y su factor, vendedor por vendedor.
    - *Bitácora de cambios*: quién cambió qué y cuándo, solo lectura, **nunca se borra**.
    Argumento para el comité: **gerencia cambia la política comercial sin llamar a un programador**.
    `[CAPTURA: CommissionConfigPanel, sub-pestaña Matriz]`
13. **Pestaña Simulación — "¿cuánto me va a costar?"** Selector de 3 o 6 meses de historial + botón
    Proyectar. Devuelve, por vendedor: venta neta promedio, margen bruto promedio, comisión variable
    proyectada del mes siguiente y el **% comisión sobre margen** (la tasa efectiva real). Arriba,
    el total consolidado. Declara los dos supuestos explícitos de la proyección: asume cumplimiento
    neutro (tramo Meta, 1,0×) y **no** incluye bonos ni devoluciones estimadas. Argumento: gerencia
    puede saber el costo **antes** de comprometerse, con datos propios y no con un supuesto de
    consultor. `[CAPTURA: CommissionSimulationPanel con resultados]`

### Bloque 4 — Cómo lo vive el vendedor (slides 14-16, 3 min)

14. **La pantalla del vendedor.** `Mi Meta y Comisión` (menú Ventas → Metas): meta asignada, ventas
    del mes, % de cumplimiento, cuánto falta, medidor de progreso con alerta si va bajo 70% en la
    última semana, pronóstico de cierre del mes, adelanto de la meta del mes siguiente, y su
    comisión con el tramo alcanzado. `[CAPTURA: VendorGoalDashboard]`
15. **La tarjeta que hace posible el piloto: "Con el sistema nuevo habrías ganado".** Durante el
    piloto, cada vendedor ve **en paralelo** lo que gana hoy y lo que habría ganado con el esquema
    nuevo — con el desglose línea por línea: producto, margen que dejó, tasa de su categoría, factor
    de crédito aplicado. Argumento central para el comité: el vendedor **aprende el nuevo esquema
    con su propio dinero real de ejemplo, sin arriesgar su sueldo**, durante 2-3 meses antes de que
    nada cambie. Esto es lo que baja la resistencia al cambio de una discusión a una constatación.
    `[CAPTURA: tarjeta "Con el sistema nuevo habrías ganado" con desglose expandido]`
16. **El cambio de comportamiento que se busca.** Con el esquema nuevo, al vendedor le conviene:
    priorizar categorías de margen sano, no regalar descuento (por encima del 30% la línea no
    comisiona sin aprobación), preferir contado sobre crédito, y traer clientes nuevos (bono).
    Cierra con la frase que resume el alineamiento: *"El vendedor gana más cuando la empresa gana
    más."* Visual: tabla de 4 filas "conducta que hoy no se premia / conducta que el nuevo esquema
    premia".

### Bloque 5 — Control de riesgo (slides 17-20, 4 min)

Este bloque es el que efectivamente gana la aprobación. El comité no compra el beneficio, compra la
**reversibilidad**.

17. **Las 6 salvaguardas ya implementadas.** Tabla: (1) descuento sobre el tope no comisiona sin
    aprobación; (2) línea sin costo registrado en el ERP comisiona a tasa mínima sobre valor, no se
    ignora ni se paga de más, y se reporta a gerencia para corregir el dato; (3) las devoluciones
    del mes se descuentan, con piso $0; (4) las facturas anuladas nunca entran al cálculo;
    (5) ajuste por cartera en riesgo del vendedor — diferido, se evalúa durante el piloto;
    (6) transparencia total: cada liquidación de un mes cerrado se **congela** con su desglose
    completo y no se puede recalcular después.
18. **Los contras — dilo tú antes de que lo pregunten.** Sé explícito y completo:
    - **La comisión se vuelve más difícil de calcular mentalmente.** El vendedor ya no puede estimar
      su comisión multiplicando su venta por un %; depende del mix de productos. Mitigación: la
      pantalla de desglose línea por línea y el piloto de 2-3 meses.
    - **Depende de la calidad del costo cargado en SAP.** Si un costo está mal, el margen está mal y
      la comisión está mal. Mitigación: salvaguarda 2 + reporte de líneas sin costo; **criterio de
      salida del piloto: menos del 5% de líneas sin costo**. Dato favorable: hoy el 100% de las
      líneas tienen margen calculable.
    - **El ajuste por crédito solo tiene datos reales para 2 de los 7 tramos** (contado y 30 días) —
      el ERP hoy no diferencia 45/60/90 días. Los tramos existen configurables pero sin historial
      que los valide.
    - **Puede haber ganadores y perdedores entre vendedores.** El que vende volumen de bajo margen
      gana menos que hoy; el que vende mix rentable gana más. Eso es el objetivo del cambio, pero es
      un costo político real que hay que administrar. Mitigación: la Simulación lo muestra
      **vendedor por vendedor antes de activar**, no después.
    - **Las tasas propuestas (A 13% / B 10% / C 6% / S 8%) son una propuesta técnica derivada de los
      datos, no una política validada por gerencia.** La decisión de tasa es de gerencia, no del
      sistema.
19. **Lo que este módulo NO hace** (declararlo evita expectativas falsas): no reparte comisión entre
    vendedor externo e interno cuando comparten un cliente (requiere un CRM de cotizaciones que no
    existe); no incluye bono por visitas (requiere geolocalización); no divide el pago entre el
    momento de facturar y el de cobrar (queda para una fase futura).
20. **El rollback: una sola variable.** El sistema tiene 3 modos —
    **plana** (lo actual, activo hoy por defecto) → **sombra** (calcula ambos, paga el actual,
    todos ven la comparación) → **variable** (el nuevo pasa a ser el oficial). Cambiar de modo es
    cambiar **una** variable de configuración y reiniciar el servicio; volver atrás es instantáneo y
    **no se pierde nada**: cada mes calculado queda congelado como registro histórico. Visual:
    diagrama de 3 estados con flechas bidireccionales. Mensaje: *"esto no es una puerta de un solo
    sentido."*

### Bloque 6 — El pedido concreto (slides 21-24, 3 min)

21. **El plan de piloto propuesto.** Cronograma de 5 pasos con responsable y duración:
    (1) gerencia valida/ajusta las tasas de la matriz en la pestaña Config — 1 sesión;
    (2) correr la Simulación y revisar el impacto vendedor por vendedor — 1 sesión;
    (3) activar modo **sombra** — 1 día técnico;
    (4) 2-3 meses en paralelo, con revisión mensual del reporte de divergencia (el sistema alerta
    automáticamente cuando la diferencia entre ambos esquemas supera el umbral configurado);
    (5) decisión de gerencia: activar `variable`, seguir en sombra, o volver a `plana`.
22. **Criterios de éxito medibles del piloto** (acordarlos hoy, no después):
    - % de comisión sobre margen bruto mensual dentro del rango objetivo **15-20%**;
    - menos del **5%** de líneas sin costo registrado;
    - variación de ingreso por vendedor dentro de un rango que gerencia defina como aceptable;
    - cero incidentes de liquidación no explicable (todo pago debe poder rastrearse a su desglose).
23. **La decisión que se pide hoy.** Una sola slide, tres viñetas:
    (a) aprobar la activación del **modo sombra** por 2-3 meses (no cambia ningún pago);
    (b) agendar la sesión de validación de tasas con gerencia;
    (c) designar al responsable de revisar el reporte mensual de divergencia.
    Enfatiza: **hoy no se está pidiendo cambiar la forma de pagar, se está pidiendo permiso para
    medirla en paralelo.** Ese es el pedido de menor riesgo posible.
24. **Cierre.** Vuelve a la pregunta de la slide 2 y respóndela con lo que el piloto va a demostrar
    con datos propios de la empresa.

### Anexo (slides 25-26, opcional, para preguntas)

25. **Anexo A — La matriz completa de las 22 categorías reales** con venta, margen y grupo asignado
    (tabla completa de §DATOS REALES). Es la slide a la que se salta si alguien pregunta "¿y en mi
    categoría cómo queda?".
26. **Anexo B — Trazabilidad y auditoría.** Dónde queda registrado cada cambio de configuración
    (bitácora append-only), dónde queda congelada cada liquidación, y qué reglas de negocio están
    validadas contra el sistema real.

---

## DATOS REALES (única fuente de cifras permitida)

Todos estos datos provienen del Data Warehouse real de la empresa, verificados con consultas de solo
lectura. **No los redondees hacia arriba ni los presentes como estimaciones.**

### Volumen y cobertura

| Dato | Valor real |
|---|---|
| Líneas de venta analizadas | 521.766 |
| Líneas con margen bruto calculable | 100% (0 líneas sin margen) |
| Margen mediano por línea | 18,03% |
| Productos en el catálogo | 8.151 |
| Categorías (clases) distintas | 22 |
| Reglas de comisión configuradas hoy | 23 (22 categorías + 1 comodín de respaldo) |
| Líneas con algún descuento aplicado | 68,1% (355.094 de 521.766) |
| Líneas de valor casi nulo (cortesías, redondeos) | 18,6% (96.926) — se excluyen automáticamente |
| Vendedores activos (últimos 12 meses) | 11 |
| Sucursales | 7 |
| Almacenes / bodegas | 14 operativos |

### Plazos de crédito (la limitación más importante a declarar)

| Plazo | Líneas | % |
|---|---|---|
| Contado (0 días) | 321.609 | 61,6% |
| Crédito 30 días | 200.157 | 38,4% |
| 15 / 45 / 60 / 90+ días | 0 | 0% — el ERP no los diferencia hoy |

### Las 22 categorías reales (venta neta histórica y margen global)

| Categoría | Venta neta | Margen global | Grupo asignado | Qué es |
|---|---|---|---|---|
| BAT | $20.363.690,98 | 12,23% | A | Baterías (línea principal) |
| REP | $3.302.661,63 | 19,56% | A | Repuestos generales |
| HER | $984.973,63 | 27,44% | A | Herramientas |
| SON | $299.259,35 | 18,25% | B | Aromatizantes / cuidado exterior |
| LED01 | $286.990,04 | 9,30% | B | Iluminación LED |
| KARCH | $217.151,12 | 10,13% | B | Equipos Kärcher |
| BATMO | $179.999,61 | 23,36% | B | Baterías de moto |
| EQU | $148.061,34 | 14,21% | B | Equipos de taller |
| TRICO | $126.252,14 | 53,20% | B | Plumas limpiaparabrisas |
| LUB | $117.742,18 | 14,31% | B | Lubricantes |
| ALF | $112.920,80 | **0,27%** | C | Alfombras — margen casi nulo |
| VAR | $105.904,32 | 44,04% | B | Varios / accesorios |
| RHC | $43.194,66 | 18,72% | C | Alternadores / arranques |
| LLAN | $37.923,05 | **2,96%** | C | Llantas Hankook — margen bajo |
| LED00 | $25.342,80 | 46,32% | C | Iluminación LED línea 0 |
| JON | $5.515,89 | 14,71% | C | Herramientas Jonnesway |
| AMOR | $3.445,54 | 11,10% | C | Amortiguadores |
| SER | $3.275,17 | 14,09% | S | Licencia de software (servicio) |
| CAL | $342,32 | 39,47% | C | Calefones |
| HRST | $21,63 | 32,41% | C | Repuesto único |
| PRO | $19,49 | 5,97% | C | Bujías en promoción |
| Z-999 | — | aberración contable | X | Baterías chatarra — tasa 0% explícita |

**Criterio de agrupación** (objetivo, derivado de los datos, no elegido caso por caso):
grupo **A** = venta ≥ $500.000; **B** = venta entre $50.000 y $500.000 **y** margen ≥ 5%;
**C** = el resto (bajo volumen, o margen < 5% aunque el volumen sea alto);
**S** = servicio/licencia; **X** = excluida.

### Parámetros configurables y sus valores por defecto

| Parámetro | Valor | Qué controla |
|---|---|---|
| Tasas por grupo | A 13% · B 10% · C 6% · S 8% · X 0% | % sobre la base (margen o valor) |
| Factor estratégico | 1,00 neutral (rango 0,5-1,5) | Empuje/freno temporal por categoría |
| Factor tipo de vendedor | Externo 1,00 · Interno 0,70 | Costo de estructura del vendedor |
| Ajuste de meta por tipo | Externo ×1,10 · Interno ×0,95 | Meta diferenciada |
| Vendedor nuevo | 60% del promedio del equipo, 3 meses | Período de adaptación |
| Multiplicador por cumplimiento | Excelente 1,2× · Meta 1,0× · Cerca 0,7× · Lejos 0,0× | Tramos de cumplimiento |
| Tope de descuento | 30% | Sobre este umbral la línea no comisiona sin aprobación |
| Tasa mínima sin costo | 5% sobre valor | Salvaguarda para líneas sin costo en el ERP |
| Umbral de exclusión | $1,00 | Bajo este monto la línea se excluye (grupo X) |
| Bono cliente nuevo/reactivado | $50 fijo | Cliente sin compras en 6 meses cuenta como nuevo |
| Bono venta cruzada | 5% | Sobre ventas originadas en sugerencias aceptadas |
| Bono cobranza sana | 5% si cobra en menos de 30 días promedio | Incentivo de recuperación de cartera |
| Factor de crédito | Contado 1,00 · 30 días 0,85 | Único tramo con datos reales además de contado |
| Factor de Presión Comercial | 0% a 25% | Ajuste discrecional de gerencia sobre todas las metas |
| KPI de sanidad del piloto | 15-20% de comisión sobre margen bruto | Rango objetivo a vigilar |

### Ejemplo real disponible para la demostración en vivo

El sistema tiene datos reales verificados de un vendedor concreto para el período en curso
(meta mensual ≈ $58.098,83 y venta real acumulada ≈ $54.976,83, es decir ~94,6% de cumplimiento —
tramo "Meta"). **Recomendación: no pongas el nombre real de un vendedor en la diapositiva
proyectada**; usa "Vendedor A" en pantalla y deja el nombre real solo para la demo en vivo si
gerencia lo pide. Exponer la comisión nominal de una persona identificada frente a un comité, en una
slide que después circula por correo, es un problema innecesario.

### Estado actual del sistema (verificado)

- El módulo de **metas automáticas** y el **esquema plano de comisión** ya están **en producción y
  operando**.
- El esquema **variable está completamente implementado y probado** (32 pruebas automatizadas del
  motor de cálculo, incluidos casos de control con resultado numérico verificado), pero **inactivo
  por configuración** — hoy no afecta ningún pago.
- La matriz de las 22 categorías ya está **poblada y auditada** con los datos reales de arriba.
- Falta **únicamente la decisión de gerencia** para activar el piloto. No hay desarrollo pendiente
  que bloquee la activación.

---

## ENTREGABLES ADICIONALES

Además de las diapositivas, produce:

### 1. Resumen ejecutivo de una página

Para imprimir y dejar sobre la mesa. Debe caber en una carilla y contener: el problema en 2 frases,
la propuesta en 3 viñetas, el costo estimado y cómo se mide, los 3 riesgos principales con su
mitigación, la decisión que se solicita, y el mecanismo de reversa. Sin gráficos.

### 2. Las 10 preguntas difíciles con respuesta preparada

Anticipa lo que el comité va a preguntar y prepara la respuesta corta (2-3 frases), anclada en
§DATOS REALES. Cubre obligatoriamente:

1. "¿Cuánto más nos va a costar esto en total?" (respuesta: lo dice la Simulación con datos propios
   antes de activar; el rango objetivo de control es 15-20% de comisión sobre margen).
2. "¿Algún vendedor va a ganar menos? ¿Cuánto menos?"
3. "¿Qué pasa si el costo en SAP está mal cargado?"
4. "¿Y si los vendedores se molestan y se van?"
5. "¿Quién controla las tasas: el sistema o nosotros?"
6. "Si no funciona, ¿cuánto cuesta volver atrás?"
7. "¿Por qué no simplemente subimos el % del esquema actual?"
8. "¿Cómo le explico a un vendedor por qué ganó menos este mes?"
9. "¿Esto es un modelo de inteligencia artificial que decide solo?" (respuesta: no — el cálculo de
   comisión es aritmética determinista y auditable; la estadística se usa para *sugerir* metas, y
   toda meta requiere aprobación humana).
10. "¿Qué necesitamos hacer nosotros para arrancar?"

### 3. Checklist de preparación previa a la reunión

Lista de lo que hay que tener listo antes de presentar: qué capturas de pantalla tomar (con la ruta
de cada pantalla), correr la Simulación con datos frescos y anotar el total, verificar que el
reporte de líneas sin costo esté por debajo del 5%, y tener el sistema accesible para una demo en
vivo de 3 minutos por si el comité la pide.

---

## Notas de mantenimiento de este prompt

- Las cifras de §DATOS REALES corresponden al estado del Data Warehouse al **2026-07-29**. Antes de
  usar el prompt, verificar que sigan vigentes — especialmente el volumen de líneas, el % de líneas
  sin costo (criterio de salida del piloto) y la cobertura de plazos de crédito, que cambian si el
  ERP empieza a registrar más formas de pago.
- Si gerencia ajusta las tasas de la matriz durante la sesión de validación, actualizar la tabla de
  parámetros antes de regenerar cualquier versión de la presentación.
- Fuentes originales de cada dato (para re-verificar):
  `docs/manual_metas_y_comisiones.md` (paneles, fórmula, parámetros),
  `docs/auditoria/30_comisiones_variables.md` (cobertura de margen, plazos de crédito, descuentos),
  `docs/features/matriz_categorias_comision_variable.md` (las 22 categorías y el criterio de
  agrupación),
  `docs/features/plan_integracion_comisiones_variables.md` (salvaguardas, riesgos, brechas).
