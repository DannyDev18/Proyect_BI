# transformers/fact_transformer.py
import logging
import pandas as pd
import numpy as np
from transformers.dim_tiempo import normalizar_fechas, normalizar_numericos, normalizar_strings

logger = logging.getLogger("ETLOrchestrator")

def transformar_ventas_detalle(df: pd.DataFrame) -> pd.DataFrame:
    # Auditoría 10: el extractor trae nombres crudos de SAP para llaves que
    # resolver_llaves_hecho()/el loader esperan con otro nombre — sin este rename, la fila
    # nunca resuelve formapago_sk (columna 'codforpag' inexistente, no cae ni al centinela -1
    # porque ese fallback solo actúa si la columna existe) y num_factura llega NULL (columna
    # NOT NULL de Fact_Ventas_Detalle).
    df = df.rename(columns={'numfac': 'num_factura', 'conpag': 'codforpag'})

    # Auditoría 08 (F17): normalizar llaves de negocio usadas para resolver surrogate keys;
    # sin esto, diferencias de espacios/mayúsculas hacen caer la fila al centinela -1.
    df = normalizar_strings(df, ['codemp', 'codart', 'codcli', 'codven', 'codalm', 'codforpag', 'num_factura'])

    # Auditoría 10 (docs/auditoria/10_auditoria_ventas_detalle_calculo.md): el extractor trae
    # las columnas crudas de SAP (cantid, preuni, desren, totren, ultcos, porceiva), no los
    # campos ya nombrados/calculados que el resto de esta función espera. Fórmula validada
    # contra una muestra real de renglonesfacturas (codemp='01', estado='P'):
    #   - subtotal_neto = totren: SAP ya lo calcula post-descuento (desren es % de descuento,
    #     no un monto — cantid*preuni*(1-desren/100) coincide exactamente con totren).
    #   - valor_iva usa r.porceiva (línea, ya resuelto como fracción decimal, ej. 0.15), NO
    #     e.poriva (encabezado: es el código de tarifa, FK a iva.codiva, no la tasa).
    #   - costo_total/margen_bruto no existen en SAP a nivel de línea (ultcos es por artículo);
    #     se derivan aquí, no hay forma de "solo traerlos".
    df['cantidad'] = pd.to_numeric(df.get('cantid'), errors='coerce')
    df['precio_unitario'] = pd.to_numeric(df.get('preuni'), errors='coerce')
    df['subtotal_bruto'] = df['cantidad'] * df['precio_unitario']
    df['subtotal_neto'] = pd.to_numeric(df.get('totren'), errors='coerce')
    df['valor_descuento'] = df['subtotal_bruto'] - df['subtotal_neto']
    df['valor_iva'] = df['subtotal_neto'] * pd.to_numeric(df.get('porceiva'), errors='coerce').fillna(0.0)
    df['total_linea'] = df['subtotal_neto'] + df['valor_iva']

    # Auditoría 34 (H-15): regla de negocio #5 ya validada ("el costo de inventario solo
    # aplica cuando renglonesfacturas.desinv = 'S'") -- antes se calculaba costo/margen
    # para TODAS las líneas sin condicionar por 'desinv', atribuyendo costo indebido a
    # líneas no inventariables (904 líneas, ~$68 mil, confirmado contra Producción). Si
    # 'desinv' no viene en el origen (p.ej. un extractor que aún no lo trae), se asume
    # 'S' (comportamiento anterior) para no romper otros consumidores en silencio.
    desinv = df['desinv'].astype(str).str.strip().str.upper() if 'desinv' in df.columns else pd.Series('S', index=df.index)
    aplica_costo = desinv == 'S'
    costo_unitario_bruto = pd.to_numeric(df.get('ultcos'), errors='coerce')
    df['costo_unitario'] = costo_unitario_bruto.where(aplica_costo)
    df['costo_total'] = (df['cantidad'] * costo_unitario_bruto).where(aplica_costo)
    df['margen_bruto'] = np.where(aplica_costo, df['subtotal_neto'] - df['costo_total'], np.nan)

    # Auditoría 34 (H-13): 'es_linea_servicio' se deriva de 'bienser' A NIVEL DE LÍNEA
    # (renglonesfacturas.bienser: 'S'=servicio, 'B'=bien) -- NO de dim_producto.es_servicio,
    # que depende de articulos.bienser, un flag del maestro casi sin uso real en Producción
    # (1 fila en 'S' de 8.152 artículos, contra 58.407 líneas reales en 'S'). Es la fuente
    # que commission_engine necesita para el grupo S (RN-CM1); antes ninguna línea real
    # activaba esa rama porque dim_producto.es_servicio era siempre False.
    df['es_linea_servicio'] = (
        df['bienser'].astype(str).str.strip().str.upper() == 'S' if 'bienser' in df.columns else False
    )

    df.drop(columns=['cantid', 'preuni', 'desren', 'totren', 'ultcos', 'porceiva', 'bienser', 'desinv'],
            errors='ignore', inplace=True)

    # Auditoría 08 (F2) / Auditoría 34 (H-15): costo_unitario/costo_total/margen_bruto pueden
    # quedar NULL a propósito -- artículo sin costeo (F2 original) o línea con desinv='N'
    # (H-15) -- y NO deben convertirse en 0.0: un margen_bruto=0.0 activaría la ruta normal
    # de comisión con base 0 en vez de la Salvaguarda 2 ("línea sin costo" -> tasa mínima
    # sobre valor) de commission_engine._calcular_linea, que depende de `margen_bruto is None`.
    # Antes 'margen_bruto' NO estaba en permitir_nulos (inconsistente con su propio comentario
    # original) -- no importaba mientras el 100% de las líneas tenía costo (auditoría 30, H1),
    # pero con H-15 aplicando NULL a 904 líneas reales (desinv='N') sí lo activa.
    df = normalizar_numericos(df, [
        'cantidad', 'precio_unitario', 'subtotal_bruto',
        'valor_descuento', 'subtotal_neto', 'valor_iva', 'total_linea',
    ])
    df = normalizar_numericos(
        df, ['costo_unitario', 'costo_total', 'margen_bruto'],
        permitir_nulos=['costo_unitario', 'costo_total', 'margen_bruto'],
    )

    # Calcular pct_margen. A diferencia de margen_bruto/costo_total (que sí pueden quedar NULL
    # cuando SAP no tiene costo del artículo — auditoría 10), pct_margen es NOT NULL por
    # convención (auditoría 07 H8): 0.0 tanto si subtotal_neto=0 como si margen_bruto es NULL.
    df['pct_margen'] = np.where(
        (df['subtotal_neto'] != 0.0) & df['margen_bruto'].notna(),
        ((df['margen_bruto'] / df['subtotal_neto']) * 100.0).round(4),
        0.0
    )
    df['pct_margen'] = df['pct_margen'].clip(-9999.9999, 9999.9999)

    # Auditoría 08 (F13, F14 — Pendiente de validar): se asume que 'cantidad' negativa indica
    # devolución y que el signo de 'cantidad' se preserva (a diferencia de
    # Fact_Movimientos_Inventario, donde sí se fuerza a magnitud positiva). Ninguna de las dos
    # reglas está confirmada contra Producción (SELECT MIN(cantid) FROM renglonesfacturas);
    # no se corrige aquí para no introducir una suposición sin evidencia.
    df['es_devolucion'] = df['cantidad'] < 0

    # Auditoría 08 (F12): Fact_Ventas_Detalle ya no acepta 'es_devolucion'/'estado_factura'
    # sueltos — requiere 'estado_documento_sk' resuelto contra Dim_Estado_Documento
    # (tipo_documento, es_devolucion, estado_factura). Este transformer expone los tres
    # atributos con esos nombres exactos para que el loader haga ese lookup; no escribe
    # directamente en columnas que ya no existen en la tabla destino.
    if 'tipo_documento' in df.columns:
        df = normalizar_strings(df, ['tipo_documento'])
    else:
        df['tipo_documento'] = '-1'
        logger.warning("transformar_ventas_detalle: 'tipo_documento' ausente en el origen; se usa el centinela '-1'.")

    if 'estado' in df.columns:
        df = df.rename(columns={'estado': 'estado_factura'})
    if 'estado_factura' not in df.columns:
        df['estado_factura'] = 'A'
    df = normalizar_strings(df, ['estado_factura'])

    return df

def transformar_inventario_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, [
        'stock_actual', 'costo_promedio', 'valor_inventario',
        'stock_minimo', 'stock_maximo', 'punto_reorden'
    ])
    
    if 'alerta_desabastecimiento' not in df.columns:
        df['alerta_desabastecimiento'] = df['stock_actual'] <= df['stock_minimo']
        
    if 'alerta_sobrestock' not in df.columns:
        df['alerta_sobrestock'] = df['stock_actual'] >= df['stock_maximo']
        
    return df

def transformar_movimientos_inventario(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['cantidad_movimiento', 'costo_unitario', 'costo_total', 'valor_venta'])
    # Auditoría 08 (F16, F17): codcli/codven (H5) y demás llaves de negocio deben normalizarse
    # igual que en dim_transformer.py, o el lookup contra Dim_Cliente/Dim_Vendedor/Dim_Producto/
    # Dim_Almacen no calza y la fila cae al centinela -1 perdiendo la relación real.
    df = normalizar_strings(df, ['tipo_movimiento', 'num_documento', 'codemp', 'codart', 'codalm', 'codcli', 'codven'])

    # La dirección del movimiento la determina 'tipdoc' (EN/AC=entrada, SA/AD=salida).
    # 'cantot' SIEMPRE es positivo en el origen, por lo que NO se puede inferir la dirección
    # por el signo (el código anterior marcaba todo como entrada). Regla validada contra
    # Producción: docs/auditoria/02_reglas_negocio_validadas.md §4.
    if 'tipdoc' in df.columns:
        tipdoc = df['tipdoc'].astype(str).str.strip().str.upper()
        df['es_entrada'] = tipdoc.isin(['EN', 'AC'])
        df['es_salida'] = tipdoc.isin(['SA', 'AD'])
    else:
        # Auditoría 08 (F15): sin 'tipdoc' no hay forma correcta de determinar la dirección
        # ('cantidad_movimiento' siempre es positiva, así que cantidad_movimiento > 0 marcaría
        # TODO como entrada — exactamente el bug que la auditoría 04 ya había corregido). Fallar
        # explícitamente en vez de aplicar en silencio una heurística que se sabe incorrecta.
        raise ValueError(
            "transformar_movimientos_inventario: falta la columna 'tipdoc' en el origen; "
            "no se puede determinar es_entrada/es_salida sin ella (ver auditoría 08, F15)."
        )

    df['cantidad_movimiento'] = df['cantidad_movimiento'].abs()
    return df

def transformar_compras(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codart', 'codpro', 'codalm', 'num_factura'])
    df = normalizar_numericos(df, ['cantidad', 'costo_unitario', 'costo_linea', 'descuento_valor', 'total_factura'])
    return df

def transformar_cobros_cxc(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codcli', 'codven', 'codforpag', 'num_transaccion', 'establ'])
    if 'dias_vencimiento' in df.columns:
        df['dias_vencimiento'] = pd.to_numeric(df['dias_vencimiento'], errors='coerce').fillna(0).astype(int)
    df = normalizar_numericos(df, ['valor_cobrado', 'saldo_documento'])
    # Auditoría 08 (F18): "días de vencimiento desconocidos" (fillna(0) arriba) se interpreta
    # como "no vencido" — regla implícita, documentada aquí pero no corregida (requeriría un
    # estado "no determinable" que el modelo actual de esta_vencido (BOOLEAN) no admite).
    if 'esta_vencido' not in df.columns:
        df['esta_vencido'] = df['dias_vencimiento'] > 0
    return df

def transformar_pagos_cxp(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codpro', 'codforpag', 'num_transaccion', 'establ'])

    # Auditoría 10: a diferencia de cuentasporcobrar (que trae 'saldodoc'/'diasvence' ya
    # calculados), cuentasporpagar NO tiene columnas equivalentes — 'dias' está NULL en el
    # 100% de la muestra revisada. valor_pagado/saldo_pendiente/dias_vencimiento se derivan:
    #   - valor_pagado = |valor_documento| (valcob siempre llega negativo en el origen)
    #   - saldo_pendiente = 0 si documento_cerrado='S' (evidencia: filas 'S' son abonos/pagos
    #     ya aplicados), si no |valor_documento| (deuda abierta)
    #   - dias_vencimiento = fecha_vencimiento - fecha_emision (cuentasporpagar.dias no sirve)
    df['fecha_emision'] = pd.to_datetime(df.get('fecha_emision'), errors='coerce')
    df['fecha_vencimiento'] = pd.to_datetime(df.get('fecha_vencimiento'), errors='coerce')
    valor_doc = pd.to_numeric(df.get('valor_documento'), errors='coerce').abs()
    df['valor_pagado'] = valor_doc
    cerrado = df.get('documento_cerrado', pd.Series('N', index=df.index)).astype(str).str.strip().str.upper()
    df['saldo_pendiente'] = np.where(cerrado == 'S', 0.0, valor_doc.fillna(0.0))
    df['dias_vencimiento'] = (df['fecha_vencimiento'] - df['fecha_emision']).dt.days
    df['dias_vencimiento'] = df['dias_vencimiento'].fillna(0).astype(int)
    df = normalizar_numericos(df, ['valor_pagado', 'saldo_pendiente'])

    # pagos_cxp_extractor.sql renombra 'fecemi' -> 'fecha_emision' con AS, pero
    # resolver_llaves_hecho() en orchestrator.py busca la columna cruda 'fecemi' (entre una
    # lista fija de nombres) para resolver fecha_sk. Sin este alias de vuelta, fecha_sk nunca
    # se resolvía y la carga fallaba por NOT NULL en una columna NOT NULL de la tabla destino.
    df['fecemi'] = df['fecha_emision']
    return df

def transformar_nomina(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['ingreso_sueldo', 'horas_extras_valor', 'comisiones_valor', 'descuento_seguro', 'liquido_a_recibir'])
    return df

def transformar_movimientos_caja(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['monto_apertura', 'monto_ingreso', 'monto_egreso', 'monto_cierre', 'diferencia_arqueo'])
    df = normalizar_strings(df, ['num_caja', 'codemp', 'establ', 'codusu', 'codforpag'])
    return df

def transformar_metas_comerciales(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['monto_meta', 'unidades_meta'])
    return df

def transformar_logs_auditoria(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['cantidad_alterada', 'valor_anterior', 'valor_nuevo'])
    df = normalizar_strings(df, ['tabla_afectada', 'tipo_operacion', 'modulo'])
    return df

def transformar_devoluciones(df: pd.DataFrame) -> pd.DataFrame:
    # Auditoría 10: encabezadodevoluciones.codcli existe en SAP pero el extractor no lo
    # seleccionaba — Fact_Devoluciones.cliente_sk es NOT NULL y nunca podía resolverse.
    df = normalizar_strings(df, ['codemp', 'codart', 'codalm', 'codcli', 'codven', 'num_nota_credito'])
    df = normalizar_numericos(df, ['cantidad_devuelta', 'total_linea_devolucion', 'costo_total_devolucion'])
    return df

def transformar_transferencias(df: pd.DataFrame) -> pd.DataFrame:
    # Auditoría 10: transferencias_extractor.sql estaba validado y listo (comentario propio del
    # archivo: "listo para conectarse a PIPELINE_CONFIG cuando se cree dicha tabla") pero nunca
    # se conectó — Fact_Transferencias existe en el DDL desde antes pero quedó en 0 filas.
    df = normalizar_strings(df, [
        'codemp', 'codart', 'codalm_origen', 'codalm_destino', 'establ',
        'num_documento', 'num_renglon'
    ])
    df = normalizar_numericos(df, ['cantidad_enviada'])
    df = normalizar_numericos(df, ['costo_unitario'], permitir_nulos=['costo_unitario'])
    df['costo_total'] = df['cantidad_enviada'] * df['costo_unitario']
    return df
