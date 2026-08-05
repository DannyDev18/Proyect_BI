# Plan — Sobrecumplimiento, umbral de pago al 90% y desglose de la comisión en el simulador

> **Estado:** propuesta, no implementada.
> **Fecha:** 2026-07-31
> **Módulo:** Metas y Comisiones (esquema de Comisiones Variables).
> **Antecedentes directos:** `docs/features/plan_integracion_comisiones_variables.md` (esquema variable),
> `docs/features/plan_comisiones_sobre_cobros.md` + `docs/auditoria/44_comisiones_sobre_cobros.md`
> (fórmula única unificada, migraciones `0008`/`0009`),
> `docs/auditoria/35_actualizacion_modulo_metas.md` (vigencia por período, snapshots inmutables).

## 1. Qué pidió el usuario (literal, y su traducción a requerimiento)

| # | Pedido | Requerimiento |
|---|---|---|
| R-1 | *"falta revisar el caso en que un vendedor excede su meta, cómo va a comisionar en este caso y qué beneficios se le puede dar"* | Definir y hacer **configurable** el tratamiento del sobrecumplimiento (>100% de la meta): hoy es un único escalón plano de 1.2× para todo lo que pase de 100%, sin importar si cumplió 101% o 250%. |
| R-2 | *"la tabla también debería colocar cómo se construye la comisión… cuánto gané de cada cosa: en venta cuánto, en cobranza cuánto, y así con los demás elementos… tanto para el mes próximo como para el mes a reconstruir, ya que hay valores demasiado elevados en algunos vendedores"* | Exponer el **desglose por componente** en el detalle del simulador (ambos modos) y **auditar los montos anómalos** que motivaron el pedido. |
| R-3 | *"un vendedor comisionará cuando alcance el 90% de la meta"* | Por debajo del 90% de cumplimiento la comisión variable es **$0**. Hoy el tramo 80–89% sí paga (multiplicador 0.7). |

**Nota de alcance:** R-3 es un cambio de **regla de negocio con impacto en dinero real**. El código actual documenta
explícitamente (docstring de `backend/app/services/commission_engine.py:1-11`) que se eligió el esquema de 4 tramos
del documento "PROPUESTA IA" por encima de la nota informal *"si las ventas son menores a 90% no pagaría la comisión"*.
Este plan **revierte esa decisión para el esquema variable** por instrucción explícita del usuario, y deja el motor
plano legacy (`calcular_comision`) intacto — ver §5.1 para la justificación de esa separación.

---

## 2. Estado actual del código (verificado, no supuesto)

### 2.1 Tramos de cumplimiento

`backend/app/services/commission_engine.py:20-22, 76-84`:

```
UMBRAL_EXCELENTE = 1.0   # >= 100%  -> EXCELENTE
UMBRAL_META      = 0.9   # 90-99%   -> META
UMBRAL_CERCA     = 0.8   # 80-89%   -> CERCA
                          # < 80%    -> LEJOS
```

Multiplicadores aplicados en el esquema variable
(`backend/app/services/commission_variable_engine.py:189-195`, valores de `backend/app/core/config.py:202-204`):

| Nivel | Rango | Multiplicador (default) | Setting |
|---|---|---|---|
| EXCELENTE | ≥ 100% | **1.20** (plano, sin importar cuánto exceda) | `COMISION_MULT_EXCELENTE` |
| META | 90–99.9% | 1.00 | — (hardcodeado) |
| CERCA | 80–89.9% | **0.70** | `COMISION_MULT_CERCA` |
| LEJOS | < 80% | 0.00 | `COMISION_PISO_LEJOS` |

Los umbrales (0.9 / 0.8 / 1.0) son **constantes de módulo**, no configuración: no hay forma de moverlos sin tocar
código, a diferencia de la matriz de categorías, los factores de crédito, los tramos de cobranza y la propia
estructura de la fórmula, que sí son tablas con vigencia (`public.comision_*`).

### 2.2 Lo que el simulador YA calcula pero NO devuelve

`calcular_comision_variable_completa` (`commission_variable_engine.py:75-241`) ya produce, por vendedor y período:

- `montos: dict[str, float]` — el monto resuelto de **cada componente** (`base_lineas_venta`, `base_cobranza`,
  `contado_agencia`, `factor_tipo_vendedor`, `multiplicador_cumplimiento`, `devoluciones`, `bonos`).
- `traza_formula: tuple[dict, ...]` — la tubería paso a paso con `{orden, componente, operador, monto, acumulado_tras_paso}`.
- `nivel: NivelCumplimiento`.
- `desglose_lineas`, `desglose_cobranza` (tramos de días de cobro).

**Todo eso se descarta** en las tres rutas del simulador: `CommissionSimulationService` solo conserva
`resultado.comision_final` (`commission_simulation_service.py:157, 235, 341`). El schema de salida
`ProyeccionVendedorResponse` (`backend/app/schemas/commission_config.py:179-188`) tiene 7 campos escalares y
ninguno de desglose. La tabla del frontend (`frontend/src/components/goals/CommissionSimulationPanel.tsx:48-56`)
muestra 6 columnas planas.

Es decir: **R-2 no requiere calcular nada nuevo, requiere dejar de descartar lo ya calculado.**

### 2.3 Hipótesis sobre "valores demasiado elevados" (a confirmar en la Fase 0)

Cuatro candidatos concretos, en orden de sospecha:

- **H-1 — `tasa_efectiva_pct` con denominador incompleto.** La columna "% comisión / margen" divide la comisión
  **total** (líneas + cobranza + contado de agencia) entre el margen bruto de **solo las líneas de venta**
  (`commission_simulation_service.py:227-233, 332-337`). Para un vendedor con mucha cobranza y poca venta del mes,
  el porcentaje se dispara sin que la comisión en dólares sea anómala. Es un defecto de presentación heredado de
  cuando el motor solo comisionaba líneas (pre-auditoría 44).
- **H-2 — `contado_agencia` a nivel de agencia completa.** `get_ventas_contado_agencia(vendedor, agencia, …)`
  atribuye a un `jefe_agencia` un porcentaje de **todas** las ventas de contado de su agencia, no solo las suyas.
  Es el diseño intencional del componente, pero produce montos de otro orden de magnitud frente a un vendedor
  externo. Debe distinguirse visualmente, no "corregirse" a ciegas.
- **H-3 — `base_cobranza` acumulada de cartera antigua.** La comisión de cobranza se paga sobre lo **efectivamente
  cobrado en el mes** (`banfec`), que puede incluir cartera de meses anteriores; un mes con recuperación fuerte
  infla el total sin relación con la venta de ese mes. Comportamiento correcto por diseño (RN-CM8..CM13), pero
  invisible hoy.
- **H-4 — proyección con cumplimiento neutro.** `proyectar_comision_variable` fuerza `venta_real == monto_meta`
  (multiplicador 1.0) a propósito; con R-3 vigente, la proyección seguiría siendo optimista frente a la realidad
  (un vendedor que hoy queda en 85% cobraría 0, pero la proyección le asigna tramo META). Debe explicitarse en la
  UI, no cambiarse: la meta del período proyectado todavía no existe.

Ninguna de las cuatro se corrige "a ojo": la Fase 0 las mide contra el EDW real antes de tocar código.

---

## 3. Diseño propuesto

### 3.1 R-3 — Umbral mínimo de pago al 90%

**Decisión:** el multiplicador de cumplimiento pasa a ser una **tabla configurable con vigencia**, igual que el
resto de la configuración de comisiones — no una constante de módulo ni un puñado de env vars. Esto resuelve R-1 y
R-3 con el mismo mecanismo y deja a gerencia mover umbrales sin desplegar código (mismo criterio que ya se aplicó a
la fórmula en la auditoría 44).

Tabla nueva `public.comision_tramos_cumplimiento` (migración `0012`), modelada sobre el patrón ya probado de
`comision_tramos_cobranza` (§`0008`):

| Columna | Tipo | Nota |
|---|---|---|
| `id` | Integer PK | |
| `perfil` | String(15) NULL | `NULL` = aplica a todos; permite tramos distintos por externo/interno/jefe_agencia a futuro sin migración nueva. |
| `pct_desde` | Numeric(6,2) | Cota inferior del tramo, en % de cumplimiento (ej. `90.00`). |
| `pct_hasta` | Numeric(6,2) NULL | `NULL` = sin tope (último tramo). |
| `multiplicador` | Numeric(6,4) | Factor aplicado al acumulado de la tubería. |
| `etiqueta` | String(30) | Nombre visible del tramo ("Sin comisión", "Meta", "Sobrecumplimiento", "Excelencia"). |
| `bono_fijo` | Numeric(12,2) | Beneficio adicional en $ del tramo (default `0.00`). Ver §3.2. |
| `vigente_desde` / `vigente_hasta` | Date | Misma semántica de vigencia que el resto del módulo. |
| `creado_por`, `fecha_creacion` | | Auditoría, igual que `0008`. |

**Semilla de la migración (el requerimiento del usuario, sin ambigüedad):**

| `pct_desde` | `pct_hasta` | `multiplicador` | `bono_fijo` | `etiqueta` |
|---|---|---|---|---|
| 0 | 90 | **0.0000** | 0 | Sin comisión (< 90% de la meta) |
| 90 | 100 | 1.0000 | 0 | Meta |
| 100 | 110 | 1.2000 | 0 | Sobrecumplimiento |
| 110 | 125 | 1.3500 | 0 | Sobrecumplimiento alto |
| 125 | *(null)* | 1.5000 | 0 | Excelencia |

El tramo `[0, 90) → 0.0` **es** R-3: el tramo CERCA (80–89.9%, 0.7×) desaparece de la semilla. No se borra del motor —
un tramo con multiplicador 0.7 sigue siendo expresable si gerencia decide reintroducirlo; simplemente ya no viene
sembrado.

**Fallback defensivo:** si la tabla queda sin filas vigentes (dato borrado a mano), el motor cae a los tramos
actuales derivados de `settings` (`COMISION_MULT_EXCELENTE`/`CERCA`/`PISO_LEJOS` + `UMBRAL_*`), con un `WARNING` en
log — mismo patrón que `COMPONENTES_FALLBACK` en `commission_variable_engine.py:45-51`. Nunca dejar a un vendedor
sin comisión por un problema de configuración.

### 3.2 R-1 — Beneficios al vendedor que excede la meta

Tres beneficios, en orden de invasividad. **El primero es obligatorio; los otros dos requieren decisión de gerencia.**

1. **Acelerador escalonado (incluido en este plan).** Es la semilla de §3.1: a mayor sobrecumplimiento, mayor
   multiplicador sobre **toda** la comisión (líneas + cobranza + contado). Reemplaza el escalón plano actual, donde
   quien cumple 101% y quien cumple 250% reciben exactamente el mismo 1.2×. Costo de implementación: nulo más allá
   de la tabla — el motor ya multiplica por un factor resuelto.

2. **Bono fijo por tramo (`bono_fijo`, columna incluida, semilla en `0.00`).** Monto en dólares que se **suma**
   al final de la tubería cuando el vendedor alcanza el tramo, equivalente variable del
   `Goal.bono_sobrecumplimiento` que ya existe en el esquema plano (`commission_engine.py:105-107`). Se integra como
   un monto más del componente `bonos` ya existente en la fórmula — **no** como un componente nuevo, para no ampliar
   `COMPONENTES_FORMULA` (el catálogo cerrado es una salvaguarda deliberada). Queda sembrado en `0.00`: activarlo es
   una decisión de gerencia, no de este plan.

3. **Comisión marginal sobre el excedente (documentado, NO implementado).** Alternativa conceptual: comisionar la
   venta que excede la meta a una tasa distinta de la venta hasta la meta. Se descarta en esta pasada porque el
   motor variable comisiona **línea a línea por margen/categoría**, no sobre un agregado de venta — separar "las
   líneas que están por encima de la meta" no tiene un criterio de negocio derivable (¿las últimas del mes por
   fecha? ¿prorrateo?). Se deja registrado para que la decisión sea explícita y no un olvido.

**Interacción con R-3 y las devoluciones:** el multiplicador se aplica en el paso `multiplicador_cumplimiento` de la
tubería, es decir **antes** de restar devoluciones y sumar bonos (orden actual de la fórmula unificada). Un tramo con
multiplicador `0.0` deja el acumulado en $0 y, con la resta de devoluciones posterior, el piso $0 de
`evaluar_formula` (`commission_engine.py:460`) garantiza que nunca resulte negativo. **Consecuencia a documentar:**
un vendedor por debajo del 90% recibe $0 pero **los bonos configurados se suman después del multiplicador** — es
decir, podría cobrar solo los bonos. Decisión propuesta: **sí, se conservan** (el bono de cliente nuevo/venta
cruzada/cobranza sana premia una conducta específica, no el cumplimiento de meta), y se hace visible en el desglose.
Si gerencia prefiere lo contrario, se resuelve moviendo el orden del componente `bonos` en el editor de fórmula,
sin código.

### 3.3 R-2 — Desglose de la construcción de la comisión en el simulador

**Backend.** `ProyeccionVendedor` (dataclass) y `ProyeccionVendedorResponse` (schema) ganan campos **aditivos**:

```python
pct_cumplimiento: float | None      # venta_real / meta (None en proyección: no hay meta futura)
nivel: str | None                   # etiqueta del tramo alcanzado
multiplicador_cumplimiento: float   # el factor efectivamente aplicado
comisiona: bool                     # False cuando el tramo alcanzado paga 0 (R-3) -> la UI lo explica
componentes: list[ComponenteComisionResponse]
```

con

```python
class ComponenteComisionResponse(BaseModel):
    orden: int
    componente: str        # clave del catálogo cerrado
    etiqueta: str          # "Venta (margen por categoría)", "Cobranza", ...
    operador: str          # sumar | restar | multiplicar
    monto: float           # $ para sumar/restar; FACTOR adimensional para multiplicar
    es_factor: bool        # True si operador == multiplicar -> la UI no lo formatea como moneda
    acumulado_tras_paso: float
```

Origen del dato: `resultado.traza_formula` tal cual (ya trae `orden/componente/operador/monto/acumulado_tras_paso`),
más un mapa `componente -> etiqueta` legible en español definido **en un solo lugar** del backend (para que la
etiqueta sea idéntica en el panel de configuración de fórmula, en el simulador y en un futuro export).

En el modo **proyección**, la traza debe ser el **promedio** de los `meses_historico` meses simulados, coherente con
`comision_variable_proyectada`, que ya es un promedio (`commission_simulation_service.py:343-344`). Se acumula por
clave de componente y se divide por `n` — **excepto los operadores `multiplicar`**, donde promediar un factor no
tiene sentido: se reporta el factor tal cual (es constante en la proyección: `factor_tipo_vendedor` fijo y
`multiplicador_cumplimiento` neutro por diseño). Este punto es el único donde el desglose de la proyección
no es una lectura directa y necesita un test propio.

Los tres puntos de entrada quedan cubiertos: `reconstruir_mes_especifico` (mes ya cerrado, valores reales),
`proyectar_comision_variable` (promedio 3/6 meses) y — por consistencia del contrato — `simular()`, que hoy alimenta
la alerta de divergencia del piloto en sombra. **`simular()` no cambia su forma de retorno** (`SimulacionVendedorMes`)
para no tocar `NotificationService._generar_divergencia_comisiones`; solo se le agrega el desglose si resulta
necesario en la Fase 3, y en ese caso con campos opcionales.

**Frontend.** `CommissionSimulationPanel.tsx`:

- La tabla gana una **fila expandible** por vendedor (clic en la fila) con el desglose paso a paso:
  `Venta (margen por categoría) + Cobranza + Contado de agencia = Base` → `× Factor tipo vendedor` →
  `× Multiplicador de cumplimiento (nivel, %)` → `− Devoluciones` → `+ Bonos` → **Comisión final**, cada paso con su
  monto y el acumulado. `DataTable` **no soporta filas expandibles hoy** (verificado) — hay que agregar un
  `renderExpanded?: (row) => ReactNode` opcional al componente compartido, en `frontend/src/components/ui/DataTable.tsx`,
  sin romper a ningún consumidor actual.
- Columnas nuevas en la tabla principal: `% cumplimiento` y `Nivel` (badge; rojo cuando `comisiona === false`).
- Corrección de H-1 (§2.3): renombrar la columna a **"% comisión / margen de venta"** y agregar `headerTitle`
  explicando que el numerador incluye cobranza y contado de agencia, que no tienen margen de línea asociado. La
  alternativa —cambiar el denominador— se descarta: no existe un "margen" de la cobranza (es recuperación de cartera
  ya facturada). Adicionalmente, marcar la celda con un indicador cuando `base_cobranza + contado_agencia` supere el
  50% de la comisión, señalando que la tasa no es comparable con la de un vendedor puramente de líneas.

---

## 4. Fases de ejecución

### Fase 0 — Auditoría previa (obligatoria, antes de tocar código)

Reporte nuevo `docs/auditoria/45_sobrecumplimiento_umbral_y_desglose.md`. Solo `SELECT` contra el EDW y ejecución
de los servicios en modo lectura dentro del contenedor `bi_backend`.

- **A-0.1 (R-3, impacto en dinero):** distribución real de `% cumplimiento` por vendedor/mes en los últimos 12 meses
  cerrados. Cuántos vendedores-mes caen en 80–89.9% (los que **pasarían de cobrar 0.7× a cobrar $0**) y cuánto dinero
  representa eso. Este número es el costo real de R-3 y gerencia debe verlo antes de activarlo.
- **A-0.2 (R-1):** distribución del sobrecumplimiento >100%: cuántos vendedores-mes superan 110% y 125%, y cuánto
  costaría la escala propuesta (1.2/1.35/1.5) frente al 1.2 plano actual.
- **A-0.3 (R-2, "valores elevados"):** para el mes que motivó el reporte, tabla por vendedor con la composición
  `base_lineas_venta / base_cobranza / contado_agencia` y su peso relativo. Confirmar o descartar H-1..H-4 de §2.3
  con números concretos. **Este es el entregable que responde directamente la observación del usuario**, incluso
  antes de que la UI exista.
- **A-0.4:** verificar que `COMISION_MODO` esté en `plana` en el entorno donde se pruebe (los cambios de tramos NO
  deben reescribir liquidaciones `oficial` ya congeladas — la inmutabilidad de `_calcular_variable` las protege,
  `commission_service.py:205-210`, pero hay que confirmarlo en la corrida real y **no** dejar artefactos de prueba en
  `comision_liquidaciones`, como ya ocurrió y se limpió en la auditoría 44).

### Fase 1 — Tramos de cumplimiento configurables (R-1 + R-3)

1. Migración Alembic `0012_comision_tramos_cumplimiento`: tabla + semilla de §3.1 (idempotente, patrón de `0008`).
2. Modelo SQLAlchemy en `backend/app/models/commission_config.py`.
3. `CommissionConfigRepository`: `get_tramos_cumplimiento(perfil, fecha)` (resolución por vigencia, misma firma que
   `get_tramos_cobranza_as_rangos`) + `replace_tramos_cumplimiento(...)` con escritura en
   `public.comision_config_auditoria` (bitácora ya existente).
4. `commission_engine.py`: `resolver_tramo_cumplimiento(fraccion, tramos) -> TramoCumplimiento` (función **pura**,
   sin BD, con el fallback a las constantes actuales). `calcular_nivel`/`NivelCumplimiento` **se conservan** — los
   usa el motor plano legacy y `calcular_comision_variable` (ruta legacy de la fórmula `'actual'`).
5. `commission_variable_engine.py`: el bloque `multiplicador_cumplimiento` (líneas 172-195) pasa a resolver el
   multiplicador desde los tramos; `ResultadoComisionVariable` gana `tramo` (etiqueta, multiplicador, `bono_fijo`,
   `comisiona: bool`) y `pct_cumplimiento`. Nuevo parámetro `tramos_cumplimiento=None` pre-resuelto por el llamador,
   siguiendo el mismo patrón de optimización que `matriz`/`rangos_credito` (**crítico**: el simulador itera decenas
   de vendedores por período; hay 2 tests unitarios que verifican `call_count == 1` y fallarán si se resuelve por
   vendedor — ver auditoría 44).
6. `bono_fijo` del tramo se inyecta en `calcular_bonos_periodo` (`commission_bonus.py`) como un concepto más, no como
   componente nuevo de `COMPONENTES_FORMULA`.
7. Los `settings.COMISION_MULT_*` **se conservan** como fallback documentado, no se eliminan.

### Fase 2 — API + panel de configuración de tramos

1. `GET/PUT /gerencia/goals/commission-config/tramos-cumplimiento` (mismo patrón exacto que
   `tramos-cobranza`, incluida la validación de solapes y de continuidad de rangos en
   `CommissionConfigService._validar_tramos_*`).
2. Pestaña nueva **"Tramos de cumplimiento"** en `CommissionConfigPanel.tsx` (editor de tramos con
   `pct_desde/pct_hasta/multiplicador/bono_fijo/etiqueta`), reusando el editor de tramos de cobranza ya existente.
3. Validaciones obligatorias del servicio: los tramos deben cubrir `[0, ∞)` sin huecos ni solapes; `multiplicador ≥ 0`;
   al menos un tramo vigente. Un hueco en la escala dejaría a un vendedor sin multiplicador resoluble.

### Fase 3 — Desglose en el simulador (R-2)

1. `ProyeccionVendedor` + `ProyeccionVendedorResponse` + `ComponenteComisionResponse` según §3.3; mapa
   `componente -> etiqueta` en un módulo único del backend.
2. Los tres métodos de `CommissionSimulationService` dejan de descartar `traza_formula`/`montos`; promedio por
   componente en la proyección (§3.3), valores directos en la reconstrucción.
3. Tipos TS espejo en `frontend/src/types/commissionConfig.ts`.
4. `DataTable`: soporte opcional de fila expandible (`renderExpanded`), sin cambiar el comportamiento por defecto.
5. `CommissionSimulationPanel.tsx`: fila expandible con la tubería paso a paso, columnas `% cumplimiento` y `Nivel`,
   y las correcciones de presentación de H-1 (§3.3).
6. **Sin datos inventados:** todo campo del desglose sale de `traza_formula` o de una consulta real; si un componente
   no está activo en la fórmula vigente, **no aparece** en el desglose (no se muestra como `$0.00`, que sugeriría
   erróneamente que aplica y no aportó).

### Fase 4 — Validación y documentación

- `pytest backend/tests/unit` — tests nuevos:
  - `resolver_tramo_cumplimiento`: 89.99% → $0; 90.0% → 1.0×; 100.0% → 1.2×; 125.0% → 1.5×; sin tramos → fallback.
  - fórmula completa con multiplicador 0: comisión final $0 aun con bases positivas, sin valores negativos.
  - promedio del desglose en proyección: la suma de los componentes promediados reproduce
    `comision_variable_proyectada`; los factores no se promedian.
  - **guardas de rendimiento existentes** (`call_count == 1`) siguen verdes con `tramos_cumplimiento` pre-resuelto.
- `pytest backend/tests/integration -k "commission or metas"` — contrato nuevo del simulador, `PUT` de tramos con
  validación de solapes, y bitácora de auditoría poblada.
- `tsc --noEmit` + `oxlint` + `npm run build`.
- Prueba en vivo contra el EDW real con `COMISION_MODO=sombra`, comparando un mes conocido antes/después de la
  Fase 1 (debe cambiar exactamente en los vendedores del tramo 80–89.9% y en los de >110%), **limpiando** cualquier
  fila de `comision_liquidaciones` creada por la prueba.
- Reglas nuevas **RN-CM15** (umbral mínimo de pago 90%) y **RN-CM16** (escala de sobrecumplimiento configurable) en
  `docs/auditoria/02_reglas_negocio_validadas.md` §18; corrección de la nota de RN-CM1 sobre el tramo CERCA.
- Actualizar `docs/manual_metas_y_comisiones.md` §1.3.3 (el desglose es visible para gerencia) y `CLAUDE.md`.

---

## 5. Decisiones de diseño y riesgos

### 5.1 El motor plano legacy no cambia

`calcular_comision` (esquema plano, `COMISION_MODO=plana`, el que hoy está en producción) conserva sus 4 tramos.
Razones: (a) es el esquema **vigente** y R-3 se pidió en el contexto de las comisiones variables; (b) su tasa sale de
`Goal.comision_base_pct`, configurable por meta, con una semántica distinta a la del multiplicador; (c) cambiar ambos
a la vez impide atribuir cualquier diferencia observada. Si gerencia quiere el umbral de 90% también en el plano, es
un cambio posterior de 3 líneas sobre `UMBRAL_CERCA`, con su propia medición.

**Consecuencia visible:** durante `COMISION_MODO=sombra`, un vendedor al 85% mostrará comisión plana > 0 y comisión
variable = $0. Es correcto y es exactamente la clase de divergencia que el piloto en sombra existe para exponer;
debe explicarse en la UI de `CommissionTracker.tsx`, no ocultarse.

### 5.2 Riesgos

| Riesgo | Mitigación |
|---|---|
| R-3 recorta pago real a vendedores hoy en 80–89% | A-0.1 cuantifica el impacto **antes** de aplicarlo; el cambio vive en una tabla con vigencia (`vigente_desde`), así que se aplica desde una fecha elegida por gerencia, nunca retroactivamente sobre meses ya liquidados. |
| Reescritura retroactiva de meses cerrados | Los snapshots `oficial` son inmutables (`commission_service.py:205-210`, RN-CM6). El simulador **sí** recalcula con la config de hoy — eso es su propósito declarado y ya está advertido en la UI. |
| Regresión de rendimiento en el simulador | `tramos_cumplimiento` pre-resuelto por período, igual que matriz/crédito/fórmula; tests de `call_count` ya existentes lo detectan. |
| Fórmula sin componente `multiplicador_cumplimiento` activo | Si gerencia lo desactiva en el editor de fórmula, R-3 deja de aplicar por completo. Añadir una advertencia visible en la pestaña "Fórmula" del panel. |
| Desglose expone PII o datos de otro vendedor | El endpoint ya es `only_management`; el desglose es agregado por componente, sin identidad de cliente. Sin cambio de superficie de acceso. |

### 5.3 Fuera de alcance (explícito)

- Comisión marginal sobre el excedente de la meta (§3.2, punto 3).
- Tramos de cumplimiento diferenciados por perfil (la columna `perfil` existe y admite `NULL`; la semilla usa un solo
  juego de tramos para todos, como pidió el usuario).
- Cambiar el esquema plano (§5.1).
- Export a Excel/PDF del desglose del simulador.

---

## 6. Orden de ejecución sugerido

`Fase 0` → **revisión de A-0.1/A-0.2 con el usuario** (son decisiones de dinero, no técnicas) → `Fase 1` → `Fase 2`
→ `Fase 3` → `Fase 4`.

La Fase 3 (desglose) es independiente de las Fases 1-2 y puede adelantarse si el usuario prioriza entender los
"valores elevados" antes de cambiar cómo se paga.
