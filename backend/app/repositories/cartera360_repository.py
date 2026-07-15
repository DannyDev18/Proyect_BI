# backend/app/repositories/cartera360_repository.py
"""SQL del módulo Ventas — Cartera de Clientes 360
(docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32).

H1 de la auditoría 32: la cartera de un `codven` puede tener hasta ~31,000 clientes (algunos
códigos de vendedor son en realidad cuentas de sucursal, ej. "ALMACEN EL REY"). Por eso la lista
de trabajo se calcula con UNA sola consulta agregada (estadística pura, sin modelos ML) sobre
toda la cartera; el enriquecimiento con los 3 modelos (churn/RFM/cross-sell) se hace bajo demanda,
por cliente, cuando el vendedor abre el detalle de una tarjeta (ver `CarteraVendedorService` /
`PredictionService`), nunca recorriendo la cartera completa."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.gestion_cartera_evento import GestionCarteraEvento


class Cartera360Repository:
    def __init__(self, db: Session):
        self.db = db

    def get_lista_trabajo(self, codven: str) -> list[dict[str, Any]]:
        """Cartera completa del vendedor con valor histórico (12 meses), días sin
        comprar y frecuencia habitual — todo en una sola consulta agregada (regla RN-V1,
        auditoría 32 H1). El "riesgo de fuga" que ordena la lista es la caída de
        frecuencia (estadística, `dias_sin_comprar / frecuencia_promedio`), NO la
        probabilidad del modelo `churn_rf` -- esa se consulta aparte, por cliente, solo
        cuando el vendedor abre el detalle (evita N+1 de inferencia sobre carteras de
        miles de clientes)."""
        query = """
            WITH base AS (
                SELECT
                    l.id_cliente_transaccional AS cliente_id,
                    l.nombre_cliente,
                    d.fecha_completa AS fecha,
                    f.subtotal_neto AS neto
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
                JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ve.codven = :codven AND ed.estado_documento_sk <> -1
            )
            SELECT
                cliente_id, nombre_cliente,
                COUNT(DISTINCT fecha) AS num_compras,
                MAX(fecha) AS ultima_compra,
                MIN(fecha) AS primera_compra,
                CURRENT_DATE - MAX(fecha) AS dias_sin_comprar,
                COALESCE(SUM(neto) FILTER (WHERE fecha >= CURRENT_DATE - INTERVAL '365 days'), 0) AS valor_historico
            FROM base
            GROUP BY cliente_id, nombre_cliente
        """
        rows = self.db.execute(text(query), {"codven": codven}).fetchall()
        resultado = []
        for r in rows:
            num_compras = int(r[2])
            ultima = r[3]
            primera = r[4]
            dias_sin_comprar = int(r[5])
            valor_historico = float(r[6] or 0)
            frecuencia_dias = None
            if num_compras > 1 and ultima and primera:
                frecuencia_dias = max((ultima - primera).days / (num_compras - 1), 1)
            alerta_caida_frecuencia = bool(
                frecuencia_dias and dias_sin_comprar > frecuencia_dias * 2
            )
            resultado.append({
                "cliente_id": r[0], "nombre_cliente": r[1], "num_compras": num_compras,
                "dias_sin_comprar": dias_sin_comprar, "valor_historico": round(valor_historico, 2),
                "frecuencia_promedio_dias": round(frecuencia_dias, 1) if frecuencia_dias else None,
                "alerta_caida_frecuencia": alerta_caida_frecuencia,
            })
        return resultado

    # ── Registro de gestión (mismo patrón que public.recomendaciones_eventos) ──
    def log_gestion(
        self, usuario_id: int, cliente_sk: int | None, evento: str, motivo: str | None = None,
    ) -> GestionCarteraEvento:
        registro = GestionCarteraEvento(usuario_id=usuario_id, cliente_sk=cliente_sk, evento=evento, motivo=motivo)
        self.db.add(registro)
        self.db.commit()
        self.db.refresh(registro)
        return registro

    def get_tasa_recuperacion(self, usuario_id: int | None = None) -> dict[str, Any]:
        query = self.db.query(GestionCarteraEvento.evento, GestionCarteraEvento.usuario_id)
        if usuario_id is not None:
            query = query.filter(GestionCarteraEvento.usuario_id == usuario_id)
        rows = query.all()
        total = len(rows)
        recompras = sum(1 for r in rows if r[0] == "recompro")
        return {
            "total_gestiones": total,
            "recompras": recompras,
            "tasa_recuperacion_pct": round((recompras / total) * 100, 2) if total else 0.0,
        }
