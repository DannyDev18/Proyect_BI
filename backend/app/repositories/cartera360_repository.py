# backend/app/repositories/cartera360_repository.py
"""SQL del módulo Ventas — Cartera de Clientes 360
(docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32).

H1 de la auditoría 32: la cartera de un `codven` puede tener hasta ~31,000 clientes (algunos
códigos de vendedor son en realidad cuentas de sucursal, ej. "ALMACEN EL REY"). Por eso la lista
de trabajo se calcula con UNA sola consulta agregada (estadística pura, sin modelos ML) sobre
toda la cartera; el enriquecimiento con los 3 modelos (churn/RFM/cross-sell) se hace bajo demanda,
por cliente, cuando el vendedor abre el detalle de una tarjeta (ver `CarteraVendedorService` /
`PredictionService`), nunca recorriendo la cartera completa."""
import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
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
        # Auditoría 41 (Fase 0 del refactor, hallazgo F0-2): la versión original agregaba
        # por (cliente_id, nombre_cliente) -- ambos `text`, ya unidos a `cliente_lookup`
        # ANTES de agrupar -- forzando un `Sort` de 172k filas anchas a disco (external
        # merge). Agregar primero por `cliente_sk` (entero, ya presente en `fact_ventas_
        # detalle`) y unir `cliente_lookup` DESPUÉS de agrupar reduce el ancho de la fila
        # que se ordena y el tamaño del resultado a unir -- medido: 530.8 ms -> 231.7 ms
        # de ejecución sobre la cartera más grande real (VEN01, 31.093 clientes).
        query = """
            WITH base AS (
                SELECT
                    f.cliente_sk,
                    d.fecha_completa AS fecha,
                    f.subtotal_neto AS neto
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ve.codven = :codven AND ed.estado_documento_sk <> -1
            ),
            agregado AS (
                SELECT
                    cliente_sk,
                    COUNT(DISTINCT fecha) AS num_compras,
                    MAX(fecha) AS ultima_compra,
                    MIN(fecha) AS primera_compra,
                    COALESCE(SUM(neto) FILTER (WHERE fecha >= CURRENT_DATE - INTERVAL '365 days'), 0) AS valor_historico
                FROM base
                GROUP BY cliente_sk
            )
            SELECT
                l.id_cliente_transaccional AS cliente_id, l.nombre_cliente,
                a.num_compras, a.ultima_compra, a.primera_compra,
                CURRENT_DATE - a.ultima_compra AS dias_sin_comprar,
                a.valor_historico
            FROM agregado a
            JOIN edw.dim_cliente c ON a.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
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
                "ultima_compra": ultima, "dias_sin_comprar": dias_sin_comprar,
                "valor_historico": round(valor_historico, 2),
                "frecuencia_promedio_dias": round(frecuencia_dias, 1) if frecuencia_dias else None,
                "alerta_caida_frecuencia": alerta_caida_frecuencia,
            })
        return resultado

    def get_perfil_cliente(self, cliente_id: str) -> dict[str, Any] | None:
        """Perfil agregado de UN cliente para el asistente de Venta Cruzada (Fase 1,
        docs/features/plan_refactor_venta_cruzada_ia.md CAMBIO 1). A diferencia de
        `get_lista_trabajo` (cartera de UN vendedor), aquí se agrega la historia
        completa del cliente sin filtrar por `codven` -- decisión de negocio §2.4 del
        plan: CLV histórico = `SUM(subtotal_neto)` de TODA la historia del cliente,
        no solo lo vendido por el vendedor que lo consulta (un cliente puede haber
        comprado a más de un vendedor). El ticket promedio se calcula por FACTURA
        (`num_factura`), no por línea -- una factura con 5 líneas no son 5 tickets."""
        query = """
            WITH lineas AS (
                SELECT f.num_factura, d.fecha_completa AS fecha, f.subtotal_neto AS neto,
                       p.clase AS categoria
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                WHERE l.id_cliente_transaccional = :cliente_id
                  AND ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND p.producto_sk <> -1
            ),
            facturas AS (
                SELECT num_factura, MIN(fecha) AS fecha, SUM(neto) AS total_factura
                FROM lineas GROUP BY num_factura
            ),
            categoria_favorita AS (
                SELECT categoria, SUM(neto) AS venta FROM lineas
                WHERE categoria IS NOT NULL AND categoria <> ''
                GROUP BY categoria ORDER BY venta DESC LIMIT 1
            )
            SELECT
                (SELECT COUNT(*) FROM facturas) AS num_compras,
                (SELECT MAX(fecha) FROM facturas) AS ultima_compra,
                (SELECT MIN(fecha) FROM facturas) AS primera_compra,
                (SELECT COALESCE(SUM(total_factura), 0) FROM facturas) AS valor_historico,
                (SELECT COALESCE(AVG(total_factura), 0) FROM facturas) AS ticket_promedio,
                (SELECT COUNT(*) FILTER (WHERE fecha >= CURRENT_DATE - INTERVAL '365 days') FROM facturas) AS frecuencia_12m,
                (SELECT categoria FROM categoria_favorita) AS categoria_favorita
        """
        row = self.db.execute(text(query), {"cliente_id": cliente_id}).fetchone()
        if row is None or row[0] == 0:
            return None
        num_compras = int(row[0])
        ultima_compra = row[1]
        primera_compra = row[2]
        antiguedad_dias = (datetime.date.today() - primera_compra).days if primera_compra else None
        return {
            "num_compras": num_compras,
            "ultima_compra": ultima_compra,
            "antiguedad_dias": antiguedad_dias,
            "valor_historico": round(float(row[3] or 0), 2),
            "ticket_promedio": round(float(row[4] or 0), 2),
            "frecuencia_12m": int(row[5] or 0),
            "categoria_favorita": row[6],
        }

    def get_productos_favoritos_cliente(self, cliente_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Top productos (por venta neta acumulada) del cliente, para el panel de
        perfil del asistente de Venta Cruzada (Fase 1) y el combo "Cliente Frecuente"
        de la Fase 4 (`venta_acumulada` real, usada ahí para calcular qué fracción del
        gasto histórico del cliente representan sus productos favoritos -- nunca un
        porcentaje inventado). Mismas exclusiones que el resto del repositorio (estado
        válido, sin devoluciones, catálogo vigente)."""
        rows = self.db.execute(text(
            """
            SELECT p.codart, p.nombre_articulo, SUM(f.subtotal_neto) AS venta
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            WHERE l.id_cliente_transaccional = :cliente_id
              AND ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND p.producto_sk <> -1
              AND p.es_vigente
            GROUP BY p.codart, p.nombre_articulo
            ORDER BY venta DESC
            LIMIT :limit
            """
        ), {"cliente_id": cliente_id, "limit": limit}).fetchall()
        return [{"codart": str(r[0]), "nombre": r[1] or "", "venta_acumulada": float(r[2] or 0)} for r in rows]

    # ── Registro de gestión (mismo patrón que public.recomendaciones_eventos) ──
    def log_gestion(
        self, usuario_id: int, cliente_sk: int | None, evento: str, motivo: str | None = None,
        canal: str | None = None, resultado: str | None = None,
        proxima_accion_fecha: datetime.date | None = None, nota: str | None = None,
    ) -> GestionCarteraEvento:
        """Docs/auditoria/34_actualizacion_modulo_ventas.md, H-V5: antes era un INSERT
        plano sin ninguna protección -- un doble-click en "Registrar gestión" creaba 2
        filas, inflando `total_gestiones`/`tasa_recuperacion`. Un duplicado EXACTO
        (mismo usuario/cliente/evento) dentro de `CARTERA360_DEDUPE_DOBLE_CLICK_SEGUNDOS`
        devuelve el registro ya creado en vez de insertar uno nuevo -- no es una regla de
        negocio de "una gestión por día" (el mismo evento sí puede repetirse en días
        distintos), solo protección contra el doble-click accidental."""
        limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=settings.CARTERA360_DEDUPE_DOBLE_CLICK_SEGUNDOS,
        )
        reciente = (
            self.db.query(GestionCarteraEvento)
            .filter(
                GestionCarteraEvento.usuario_id == usuario_id,
                GestionCarteraEvento.cliente_sk == cliente_sk,
                GestionCarteraEvento.evento == evento,
                GestionCarteraEvento.fecha >= limite,
            )
            .order_by(GestionCarteraEvento.fecha.desc())
            .first()
        )
        if reciente is not None:
            return reciente

        registro = GestionCarteraEvento(
            usuario_id=usuario_id, cliente_sk=cliente_sk, evento=evento, motivo=motivo,
            canal=canal, resultado=resultado, proxima_accion_fecha=proxima_accion_fecha, nota=nota,
        )
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

    # ── "Mi Ruta Inteligente de Ventas" (Fase 1-2/4/6, plan_refactor_cartera360_ruta_
    # inteligente.md) ───────────────────────────────────────────────────────────

    def get_recuperados_mes_actual_por_vendedor(self, codven: str) -> int:
        """Clientes recuperados (evento `recompro`) en el mes en curso, por los usuarios
        cuyo `id_vendedor_origen` es este `codven` (§4.1) -- valor real = 0 mientras no
        haya gestiones registradas (D-1), sube con el uso del módulo."""
        row = self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM public.gestion_cartera_eventos g
                JOIN public.usuarios u ON g.usuario_id = u.id
                WHERE u.id_vendedor_origen = :codven
                  AND g.evento = 'recompro'
                  AND EXTRACT(YEAR FROM g.fecha) = EXTRACT(YEAR FROM CURRENT_DATE)
                  AND EXTRACT(MONTH FROM g.fecha) = EXTRACT(MONTH FROM CURRENT_DATE)
                """
            ),
            {"codven": codven},
        ).fetchone()
        return int(row[0] or 0)

    def get_meta_mensual_vendedor(self, codven: str, anio: int, mes: int) -> float | None:
        """Meta mensual real del vendedor (regla 10, grano `(anio, mes,
        id_vendedor_origen)`) -- usada para prorratear el objetivo diario (§4.1). Solo
        lectura, ninguna escritura sobre `metas_comerciales_operativas` desde este módulo."""
        row = self.db.execute(
            text(
                """
                SELECT monto_meta FROM public.metas_comerciales_operativas
                WHERE anio = :anio AND mes = :mes AND id_vendedor_origen = :codven
                """
            ),
            {"anio": anio, "mes": mes, "codven": codven},
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def get_ventas_dia(self, codven: str, fecha: datetime.date) -> float:
        """Venta neta real del vendedor en la fecha dada (avance del día, §4.1)."""
        row = self.db.execute(
            text(
                """
                SELECT COALESCE(SUM(f.subtotal_neto), 0)
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ve.codven = :codven AND d.fecha_completa = :fecha AND ed.estado_documento_sk <> -1
                """
            ),
            {"codven": codven, "fecha": fecha},
        ).fetchone()
        return float(row[0] or 0)

    def get_ultima_gestion_por_cliente_ids(self, cliente_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Última gestión registrada por cliente, en UN solo lote (mismo criterio anti
        N+1 que el churn batch), resuelta directo por `cliente_id` transaccional (une
        `cliente_lookup`/`dim_cliente` aquí mismo) -- evita el N+1 que antes hacía falta
        para resolver `cliente_sk` por cliente antes de poder consultar esto. Usado para
        poblar `ultima_gestion_*`/`proxima_accion_fecha` en la ruta del día, y para
        filtrar del ranking los clientes ya gestionados hoy o con seguimiento agendado a
        futuro (§ rotación de la ruta, hallazgo post-Fase 3)."""
        if not cliente_ids:
            return {}
        rows = self.db.execute(
            text(
                """
                SELECT DISTINCT ON (l.id_cliente_transaccional)
                    l.id_cliente_transaccional, g.evento, g.fecha, g.proxima_accion_fecha
                FROM public.gestion_cartera_eventos g
                JOIN edw.dim_cliente c ON g.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                WHERE l.id_cliente_transaccional = ANY(:cliente_ids)
                ORDER BY l.id_cliente_transaccional, g.fecha DESC
                """
            ),
            {"cliente_ids": cliente_ids},
        ).fetchall()
        return {
            str(r[0]): {
                "evento": r[1],
                "fecha": r[2].isoformat() if r[2] else None,
                "proxima_accion_fecha": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        }

    def get_proximas_acciones_por_vendedor(self, codven: str) -> list[dict[str, Any]]:
        """Auditoría 43 (H43-13): agenda propia del vendedor -- última gestión registrada
        POR CLIENTE (no solo del top-N del día) con `proxima_accion_fecha` no nula,
        resuelta a `id_cliente_transaccional`/`nombre_cliente` vía `cliente_lookup`
        (mismo criterio que `get_ultima_gestion_por_cliente_ids`) y filtrada por vendedor
        vía `public.usuarios.id_vendedor_origen` (mismo join que
        `get_recuperados_mes_actual_por_vendedor`). Deliberadamente INDEPENDIENTE de
        `/ruta/hoy`: ese ranking excluye a estos mismos clientes mientras la fecha esté
        vigente (rotación de la ruta), así que no puede ser también la fuente de este
        panel -- son conjuntos complementarios por diseño."""
        rows = self.db.execute(
            text(
                """
                WITH ultima_por_cliente AS (
                    SELECT DISTINCT ON (g.cliente_sk)
                        g.cliente_sk, g.evento, g.fecha, g.proxima_accion_fecha
                    FROM public.gestion_cartera_eventos g
                    JOIN public.usuarios u ON g.usuario_id = u.id
                    WHERE u.id_vendedor_origen = :codven
                      AND g.proxima_accion_fecha IS NOT NULL
                    ORDER BY g.cliente_sk, g.fecha DESC
                )
                SELECT l.id_cliente_transaccional, l.nombre_cliente,
                       up.evento, up.fecha, up.proxima_accion_fecha
                FROM ultima_por_cliente up
                JOIN edw.dim_cliente c ON up.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                ORDER BY up.proxima_accion_fecha ASC
                """
            ),
            {"codven": codven},
        ).fetchall()
        return [
            {
                "cliente_id": str(r[0]),
                "nombre_cliente": r[1] or "",
                "ultimo_evento": r[2],
                "ultima_gestion_fecha": r[3].isoformat(),
                "proxima_accion_fecha": r[4].isoformat(),
            }
            for r in rows
        ]

    def get_timeline_cliente(self, cliente_id: str, cliente_sk: int | None, limit: int = 30) -> list[dict[str, Any]]:
        """Timeline real de un cliente (§4.6): eventos EDW (compras/devoluciones/cobros)
        + gestiones registradas, ordenados por fecha desc. Con 0 gestiones (D-1) el
        timeline igual tiene contenido real desde el día 1 -- es el diseño explícito del
        plan para que el módulo no se vea vacío en la primera semana de uso."""
        eventos: list[dict[str, Any]] = []

        compras = self.db.execute(
            text(
                """
                SELECT d.fecha_completa, f.num_factura, SUM(f.subtotal_neto) AS monto
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE l.id_cliente_transaccional = :cliente_id AND ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
                GROUP BY d.fecha_completa, f.num_factura
                ORDER BY d.fecha_completa DESC LIMIT :limit
                """
            ),
            {"cliente_id": cliente_id, "limit": limit},
        ).fetchall()
        for r in compras:
            eventos.append({
                "tipo": "compra", "fecha": r[0].isoformat(), "monto": float(r[2] or 0),
                "descripcion": f"Compra factura {r[1]}",
            })

        # Auditoría 41 (hallazgo post-Fase 3): `fact_devoluciones` NO tiene `num_factura`/
        # `subtotal_neto` (columnas de `fact_ventas_detalle`, copiadas por error) -- su
        # grano real es nota de crédito (`num_nota_credito`) y el monto es
        # `total_linea_devolucion`. Confirmado con `\d edw.fact_devoluciones`.
        devoluciones = self.db.execute(
            text(
                """
                SELECT d.fecha_completa, f.num_nota_credito, SUM(f.total_linea_devolucion) AS monto
                FROM edw.fact_devoluciones f
                JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                WHERE l.id_cliente_transaccional = :cliente_id
                GROUP BY d.fecha_completa, f.num_nota_credito
                ORDER BY d.fecha_completa DESC LIMIT :limit
                """
            ),
            {"cliente_id": cliente_id, "limit": limit},
        ).fetchall()
        for r in devoluciones:
            eventos.append({
                "tipo": "devolucion", "fecha": r[0].isoformat(), "monto": float(r[2] or 0),
                "descripcion": f"Devolución nota de crédito {r[1]}",
            })

        cobros = self.db.execute(
            text(
                """
                SELECT d.fecha_completa, f.valor_cobrado
                FROM edw.fact_cobros_cxc f
                JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
                JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                WHERE l.id_cliente_transaccional = :cliente_id
                ORDER BY d.fecha_completa DESC LIMIT :limit
                """
            ),
            {"cliente_id": cliente_id, "limit": limit},
        ).fetchall()
        for r in cobros:
            eventos.append({
                "tipo": "cobro", "fecha": r[0].isoformat(), "monto": float(r[1] or 0),
                "descripcion": "Cobro registrado",
            })

        if cliente_sk is not None:
            gestiones = (
                self.db.query(GestionCarteraEvento)
                .filter(GestionCarteraEvento.cliente_sk == cliente_sk)
                .order_by(GestionCarteraEvento.fecha.desc())
                .limit(limit)
                .all()
            )
            for g in gestiones:
                eventos.append({
                    "tipo": "gestion", "fecha": g.fecha.date().isoformat(), "monto": None,
                    "descripcion": g.nota or g.resultado or g.evento,
                    "evento_gestion": g.evento,
                })

        eventos.sort(key=lambda e: e["fecha"], reverse=True)
        return eventos[:limit]

    def get_efectividad_gestiones(self, usuario_id: int | None) -> dict[str, Any]:
        """Efectividad Comercial (§4.8): gestiones reales cruzadas con si el cliente
        gestionado terminó comprando después. `ventas` = gestiones con `evento='recompro'`
        (la única señal de conversión que el propio registro de gestión ya declara --
        no se infiere una compra por fuera de lo que el vendedor marcó, para no inventar
        una atribución que el dato no sustenta)."""
        query = self.db.query(GestionCarteraEvento)
        if usuario_id is not None:
            query = query.filter(GestionCarteraEvento.usuario_id == usuario_id)
        gestiones = query.all()
        total = len(gestiones)
        ventas = [g for g in gestiones if g.evento == "recompro"]

        por_canal: dict[str, dict[str, int]] = {}
        for g in gestiones:
            canal = g.canal or "sin_canal"
            por_canal.setdefault(canal, {"contactados": 0, "ventas": 0})
            por_canal[canal]["contactados"] += 1
            if g.evento == "recompro":
                por_canal[canal]["ventas"] += 1

        tiempos_cierre = []
        for g in ventas:
            primero = next((e for e in gestiones if e.cliente_sk == g.cliente_sk), None)
            if primero and primero.fecha and g.fecha:
                dias = (g.fecha - primero.fecha).days
                if dias >= 0:
                    tiempos_cierre.append(dias)

        return {
            "total_gestiones": total,
            "total_ventas_atribuidas": len(ventas),
            "conversion_pct": round(100 * len(ventas) / total, 2) if total else None,
            "tiempo_promedio_cierre_dias": round(sum(tiempos_cierre) / len(tiempos_cierre), 1) if tiempos_cierre else None,
            "por_canal": [
                {
                    "canal": canal, "contactados": v["contactados"], "ventas": v["ventas"],
                    "conversion_pct": round(100 * v["ventas"] / v["contactados"], 2) if v["contactados"] else 0.0,
                }
                for canal, v in por_canal.items()
            ],
        }
