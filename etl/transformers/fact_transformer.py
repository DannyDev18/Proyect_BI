# transformers/fact_transformer.py
import pandas as pd
import numpy as np
from transformers.dim_tiempo import normalizar_fechas, normalizar_numericos, normalizar_strings

def transformar_ventas_detalle(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, [
        'cantidad', 'precio_unitario', 'costo_unitario', 'subtotal_bruto',
        'valor_descuento', 'subtotal_neto', 'valor_iva', 'total_linea',
        'costo_total', 'margen_bruto'
    ])
    
    # Calcular pct_margen
    df['pct_margen'] = np.where(
        df['subtotal_neto'] != 0.0,
        ((df['margen_bruto'] / df['subtotal_neto']) * 100.0).round(4),
        0.0
    )
    df['pct_margen'] = df['pct_margen'].clip(-9999.9999, 9999.9999)
    
    df['es_devolucion'] = df['cantidad'] < 0
    # Removido: df['cantidad'] = df['cantidad'].abs() para que sumen negativamente
    
    if 'estado_factura' not in df.columns:
        df['estado_factura'] = 'A'
        
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
    df = normalizar_strings(df, ['tipo_movimiento', 'num_documento'])
    
    if 'es_entrada' not in df.columns:
        df['es_entrada'] = df['cantidad_movimiento'] > 0
    if 'es_salida' not in df.columns:
        df['es_salida'] = df['cantidad_movimiento'] <= 0
        
    df['cantidad_movimiento'] = df['cantidad_movimiento'].abs()
    return df

def transformar_compras(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['cantidad', 'costo_unitario', 'costo_linea', 'descuento_valor', 'total_factura'])
    df = normalizar_strings(df, ['num_factura'])
    return df

def transformar_cobros_cxc(df: pd.DataFrame) -> pd.DataFrame:
    if 'dias_vencimiento' in df.columns:
        df['dias_vencimiento'] = pd.to_numeric(df['dias_vencimiento'], errors='coerce').fillna(0).astype(int)
    df = normalizar_numericos(df, ['valor_cobrado', 'saldo_documento'])
    df = normalizar_strings(df, ['num_transaccion'])
    if 'esta_vencido' not in df.columns:
        df['esta_vencido'] = df['dias_vencimiento'] > 0
    return df

def transformar_pagos_cxp(df: pd.DataFrame) -> pd.DataFrame:
    if 'dias_vencimiento' in df.columns:
        df['dias_vencimiento'] = pd.to_numeric(df['dias_vencimiento'], errors='coerce').fillna(0).astype(int)
    df = normalizar_numericos(df, ['valor_pagado', 'saldo_pendiente'])
    df = normalizar_strings(df, ['num_transaccion'])
    return df

def transformar_nomina(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['ingreso_sueldo', 'horas_extras_valor', 'comisiones_valor', 'descuento_seguro', 'liquido_a_recibir'])
    return df

def transformar_movimientos_caja(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['monto_apertura', 'monto_ingreso', 'monto_egreso', 'monto_cierre', 'diferencia_arqueo'])
    df = normalizar_strings(df, ['num_caja'])
    return df

def transformar_metas_comerciales(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['monto_meta', 'unidades_meta'])
    return df

def transformar_logs_auditoria(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['cantidad_alterada', 'valor_anterior', 'valor_nuevo'])
    df = normalizar_strings(df, ['tabla_afectada', 'tipo_operacion', 'modulo'])
    return df

def transformar_devoluciones(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_numericos(df, ['cantidad_devuelta', 'total_linea_devolucion', 'costo_total_devolucion'])
    df = normalizar_strings(df, ['num_nota_credito'])
    return df
