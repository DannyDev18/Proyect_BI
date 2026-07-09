# Checklist de revisión del modelo dimensional (Kimball)

Para cada problema detectado, reportar siempre: **qué está mal, por qué, impacto y propuesta de
mejora**. El modelo de referencia del proyecto está en `docs/arquitectura_dw.md` (constelación de
hechos: 11 dims + 11 facts) — compara el DDL real (`edw/02_dimensiones.sql`, `edw/03_hechos.sql`)
contra ese diseño y contra este checklist.

## 1. Grain (granularidad) — revisar PRIMERO

- ¿Está declarado el grain de cada tabla de hechos? (En este proyecto: `fact_ventas_detalle` =
  línea de factura; `fact_inventario_snapshot` = artículo/sucursal/almacén/día; etc.)
- Verificar empíricamente: `SELECT <llaves del grain>, COUNT(*) ... HAVING COUNT(*) > 1`.
  Si hay más de una fila por combinación del grain sin justificación, el grain real no es el
  declarado → todas las agregaciones downstream son sospechosas.
- ¿Se mezclan granularidades en una misma fact (líneas junto a totales de cabecera)? Eso duplica
  montos al sumar.
- Métricas no aditivas (`precio_unitario`, `pct_margen`, `costo_promedio`): confirmar que ningún
  consumidor (servicio, dashboard, modelo ML) las está SUMANDO.
- Semi-aditivas (`stock_actual`, `saldo_documento`, `monto_apertura/cierre`): solo agregables con
  último-valor/promedio en el tiempo, nunca SUM sobre la dimensión fecha.

## 2. Surrogate keys y business keys

- Toda dim con SK entera propia (`*_sk` SERIAL); los hechos referencian SKs, nunca códigos SAP.
- Business key (`codemp`+código natural) con UNIQUE en dims tipo 1; en SCD2 la unicidad es por
  (business key, versión) — verificar que existe al menos un índice/constraint que impida
  duplicar la misma versión.
- Existe la fila centinela `-1` en cada dimensión y los hechos la usan para llaves no resueltas
  (medir % — ver validaciones_sql.md §4).

## 3. Slowly Changing Dimensions

- SCD2 declaradas: `dim_producto`, `dim_cliente`. Verificar: una sola fila `es_vigente=TRUE` por
  business key; vigencias sin solapamiento ni huecos; los hechos históricos apuntan a la versión
  vigente EN LA FECHA del hecho (no a la actual).
- Dims tratadas como tipo 1 (sobrescritura): ¿hay atributos que el negocio necesita
  históricamente (p.ej. `comision` del vendedor para liquidar comisiones pasadas)? Si sí, es un
  candidato a SCD2 o mini-dimension → hallazgo.
- ¿El loader SCD2 cierra la versión anterior (set `fecha_fin_vigencia`, `es_vigente=FALSE`) en la
  misma transacción que inserta la nueva?

## 4. Conformed dimensions

- `dim_fecha`, `dim_producto`, `dim_sucursal` son compartidas entre facts: mismo significado y
  mismas SKs en todas. Señal de violación: dos facts que se cruzan por una dim común dan
  totales inconsistentes para el mismo recorte.
- Atributos con el mismo nombre en dims distintas deben significar lo mismo (`estado`, `ciudad`).

## 5. Estrella vs copo de nieve

- El diseño es estrella: las dims deben estar desnormalizadas (la jerarquía
  clase/subclase vive DENTRO de `dim_producto`, no en tablas aparte). Una dim que referencia a
  otra dim (snowflaking) es un hallazgo salvo justificación explícita.
- Joins fact→fact directos son violación del modelo; los hechos se relacionan solo a través de
  dimensiones conformadas (drill-across).

## 6. Degenerate dimensions

- `num_factura`, `num_documento`, `num_transaccion`, `num_nota_credito` en las facts son
  dimensiones degeneradas legítimas (identificador operativo sin atributos propios). Correcto
  mantenerlas en la fact. Hallazgo si: (a) se creó una dim aparte solo para el número de
  documento, o (b) hay atributos del documento (tipo, condiciones) repetidos en la fact que
  merecerían dimensión propia.

## 7. Junk dimensions

- Grupos de flags/códigos de baja cardinalidad dispersos en la fact (`es_devolucion`,
  `estado_factura`, `tipo_documento` en `fact_ventas_detalle`) son candidatos a junk dimension.
  Reportar como prioridad Baja (mejora, no error) salvo que causen problemas reales de ancho de
  fila o inconsistencia.

## 8. Mini dimensions

- Si un atributo volátil de una dim grande (p.ej. `limite_credito` de `dim_cliente`, 73k filas
  SCD2) genera explosión de versiones, proponer mini-dimension para los atributos volátiles.
  Detectar: `SELECT codcli, COUNT(*) FROM dim_cliente GROUP BY codcli ORDER BY 2 DESC` — muchas
  versiones por cliente = síntoma.

## 9. Bridge tables

- Relaciones N:M (p.ej. varios vendedores por factura, si existiera) requieren bridge con factor
  de asignación. Si el modelo las resolvió duplicando filas de hecho o eligiendo una arbitraria,
  es hallazgo Alta (montos duplicados o atribución incorrecta).

## 10. Aggregate facts

- Si existen tablas/vistas agregadas, deben derivar de la fact atómica y reconciliar exactamente
  con ella (misma suma para el mismo recorte). Agregados que se cargan por un camino ETL distinto
  al de la fact base son riesgo de divergencia → verificar con SQL.

## 11. Relaciones y cardinalidad

- Toda FK del hecho debe existir físicamente (REFERENCES) y estar indexada (ver
  `edw/04_indices.sql`).
- Cardinalidad esperada dim:fact = 1:N. Verificar que ningún join fact→dim multiplica filas
  (señal: `COUNT(*)` de la fact cambia al hacer join — típico con SCD2 mal filtrada, hay que
  filtrar por vigencia o unir por SK exacta, nunca por business key).
- Relaciones faltantes: hechos con columnas de código natural (`codalm`, `codven`...) que no
  fueron convertidas a SK — señal de dimensión faltante o join omitido en el ETL.
