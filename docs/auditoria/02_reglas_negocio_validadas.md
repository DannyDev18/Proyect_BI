# Reglas de Negocio Validadas contra Producción (SAP SQL Anywhere)

- **Fecha:** 2026-07-08
- **Método:** consultas `SELECT` de solo lectura contra la BD origen (`DB_SERVER=xp_plus`, `db_microplus`, `172.16.50.5:4016`, empresa `codemp='01'`). No se ejecutó ninguna escritura.
- **Propósito:** documentar las reglas de negocio que antes estaban implícitas o hardcodeadas sin explicación (requisito CLAUDE.md: *toda regla de negocio debe estar documentada*). Estas reglas sustentan las correcciones de los extractores.

---

## 1. Estado de documentos (`estado`)

`encabezadofacturas.estado`:

| estado | registros | significado |
|---|---|---|
| `P` | 234 886 | **Procesada / válida** |
| `A` | 8 | **Anulada** |

**Regla:** filtrar `estado = 'P'` es correcto para excluir documentos anulados. Se mantiene, pero ahora **documentado y parametrizable** (`ESTADO_VALIDO`).

## 2. Empresa (`codemp`)

Toda la operación validada corresponde a `codemp = '01'`. Se **parametriza** vía `config.CODEMP` (token `{CODEMP}` en los extractores) para no dejarlo hardcodeado y permitir multi-empresa futura.

## 3. Tipos de movimiento de Kardex (`kardex.tiporg`)

| tiporg | registros | significado | dirección |
|---|---|---|---|
| `FAC` | 461 466 | Venta / facturación | Salida |
| `TRA` | 330 754 | Transferencia entre bodegas | Entrada+Salida (par) |
| `CPA` | 129 349 | Compra | Entrada |
| `DEV` | 8 429 | Devolución (nota de crédito) | Entrada |
| `BOD` | 7 545 | Ajuste de bodega / inventario | Entrada (mayoría) |
| `EGR` | 5 143 | Egreso | Salida |
| `ING` | 3 979 | Ingreso | Entrada |
| `DEC` | 1 167 | Ajuste / decremento | Salida (mayoría) |

## 4. Dirección del movimiento (`kardex.tipdoc`) — HALLAZGO CLAVE

`cantot` **siempre es positivo** (magnitud, no lleva signo). La dirección se determina por `tipdoc`:

| tipdoc | significado | tiporg asociados |
|---|---|---|
| `EN` | **Entrada** | CPA, DEV, ING, BOD, TRA (destino) |
| `SA` | **Salida** | FAC, EGR, DEC, TRA (origen) |
| `AC` | Ajuste (+) | BOD |
| `AD` | Ajuste (−) | DEC |

**Regla derivada para el DW:**
- `entrada = cantot` cuando `tipdoc IN ('EN','AC')`, si no `0`.
- `salida  = cantot` cuando `tipdoc IN ('SA','AD')`, si no `0`.

## 5. Transferencias (`tiporg = 'TRA'`) — estructura

Cada ítem transferido (`numdoc` + `numren`) genera **exactamente 2 filas** con la misma `cantot`:
- La fila con `tipdoc = 'SA'` → **bodega origen** (`codalm`).
- La fila con `tipdoc = 'EN'` → **bodega destino** (`codalm`).

Balance validado: `TRA` = 165 377 filas `EN` + 165 377 filas `SA` (perfectamente pareado).

**Regla derivada:** una transferencia se reconstruye agrupando por `(codemp, numdoc, numren, codart)` y pivotando `codalm` según `tipdoc` (SA=origen, EN=destino), con `cantidad_enviada = cantot`.
**Limitación [PENDIENTE ERP]:** el kardex no expone *cantidad solicitada* ni *estado* de la transferencia; solo la cantidad efectivamente movida.

## 6. Descarga de inventario (`renglonesfacturas.desinv`)

| desinv | registros | significado |
|---|---|---|
| `S` | 519 517 | La línea **sí** descarga inventario (afecta costo/stock) |
| `N` | 915 | La línea **no** descarga inventario (servicio/no inventariable) |

**Regla:** el costo de inventario solo aplica cuando `desinv = 'S'`. Documentado.

## 7. Existencias / stock — fuente confirmada

Existe la vista **`vi_mv_existencias`** con columnas: `codemp, codalm, codart, existe (stock), nomalm`.
- Provee **stock por bodega** directamente.
- **No** incluye costo → el costo/valor de inventario se obtiene de `articulos.ultcos` (último costo).
- Es la fuente para el nuevo `existencias_extractor.sql` (snapshot de inventario).

## 8. Integridad de claves (validado)

- `encabezadofacturas (codemp, numfac)`: **0 duplicados** → los JOIN cabecera↔detalle no multiplican filas.
- `articulos (codemp, codart)`: **0 duplicados** → el `LEFT JOIN articulos` no duplica renglones.

Esto **descarta** el riesgo de duplicación por JOIN señalado como *[VALIDAR]* en `01_auditoria_extractores.md` (§4.1/§4.2).

## 9. Costo de artículo (`articulos.ultcos`)

`ultcos` = **último costo** (no promedio). El alias `costo_promedio` del extractor es incorrecto y se renombra a `ultimo_costo`.
