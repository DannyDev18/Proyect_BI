# backend/app/repositories/catalog_repository.py
"""Catálogos de solo lectura sobre el EDW usados por el panel Administrador para
validar y enlazar cuentas de la plataforma (public.usuarios) con dimensiones del
EDW: edw.Dim_Vendedor (rol ventas) y edw.Dim_Almacen (rol bodega)."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_vendedor_activo(self, codven: str) -> dict[str, Any] | None:
        """Vendedor vigente (regla 12: excluye el centinela -1) con codven exacto,
        únicamente si está activo (edw.Dim_Vendedor.activo)."""
        row = self.db.execute(text(
            "SELECT codven, nombre_vendedor, activo FROM edw.dim_vendedor "
            "WHERE codven = :codven AND vendedor_sk <> -1"
        ), {"codven": codven}).fetchone()
        if not row:
            return None
        return {"codven": str(row[0]), "nombre_vendedor": row[1], "activo": bool(row[2])}

    def get_almacen(self, codalm: str) -> dict[str, Any] | None:
        """Almacén vigente (regla 12: excluye el centinela -1) con codalm exacto."""
        row = self.db.execute(text(
            "SELECT codalm, nombre_almacen FROM edw.dim_almacen "
            "WHERE codalm = :codalm AND almacen_sk <> -1"
        ), {"codalm": codalm}).fetchone()
        if not row:
            return None
        return {"codalm": str(row[0]), "nombre_almacen": row[1]}

    def list_almacenes(self) -> list[dict[str, Any]]:
        """Catálogo de almacenes (codalm + nombre) para poblar el selector del
        formulario de creación de usuarios bodega en el panel Administrador."""
        res = self.db.execute(text(
            "SELECT codalm, nombre_almacen FROM edw.dim_almacen "
            "WHERE almacen_sk <> -1 ORDER BY nombre_almacen"
        )).fetchall()
        return [{"codalm": str(r[0]), "nombre_almacen": r[1]} for r in res]

    def get_products_info(self, codarts: list[str]) -> dict[str, dict[str, Any]]:
        """Enriquecimiento de catálogo (nombre, precio, categoría, margen unitario) para
        el módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md): solo
        producto vigente (`es_vigente`, excluye el centinela `-1`, regla 7/12 CLAUDE.md).
        `margen_unitario` es None cuando `costo_promedio` es NULL/0 -- el servicio NO debe
        inventar un costo (auditoría 25 H25-4), solo ordenar por lift/score en ese caso."""
        if not codarts:
            return {}
        rows = self.db.execute(text(
            """
            SELECT codart, nombre_articulo, clase, nombre_clase, precio_oficial, costo_promedio
            FROM edw.dim_producto
            WHERE es_vigente AND producto_sk <> -1 AND codart = ANY(:codarts)
            """
        ), {"codarts": codarts}).fetchall()
        info: dict[str, dict[str, Any]] = {}
        for r in rows:
            precio = float(r[4]) if r[4] is not None else 0.0
            costo = float(r[5]) if r[5] is not None else None
            info[str(r[0])] = {
                "codart": str(r[0]),
                "nombre": r[1] or "",
                "categoria": r[3] or r[2] or "",
                "precio": precio,
                "margen_unitario": (precio - costo) if costo is not None and costo > 0 else None,
            }
        return info

    def search_productos(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Autocompletar producto por código o nombre (asistente de Venta Cruzada,
        docs/auditoria/25_modulo_cross_selling.md §2.5) -- solo catálogo vigente."""
        like = f"%{query}%"
        rows = self.db.execute(text(
            """
            SELECT codart, nombre_articulo, clase, nombre_clase, precio_oficial
            FROM edw.dim_producto
            WHERE es_vigente AND producto_sk <> -1
              AND (codart ILIKE :like OR nombre_articulo ILIKE :like)
            ORDER BY nombre_articulo
            LIMIT :limit
            """
        ), {"like": like, "limit": limit}).fetchall()
        return [
            {
                "codart": str(r[0]), "nombre": r[1] or "",
                "categoria": r[3] or r[2] or "", "precio": float(r[4]) if r[4] is not None else 0.0,
            }
            for r in rows
        ]

    def get_cliente_sk_vigente(self, cliente_id: str) -> int | None:
        """Resuelve `cliente_sk` vigente (SCD2) a partir del id transaccional público
        (`public.cliente_lookup`), para telemetría del módulo de Venta Cruzada."""
        row = self.db.execute(text(
            """
            SELECT c.cliente_sk
            FROM public.cliente_lookup l
            JOIN edw.dim_cliente c ON c.hash_anonimo = l.hash_anonimo
            WHERE l.id_cliente_transaccional = :cliente_id AND c.es_vigente
            LIMIT 1
            """
        ), {"cliente_id": cliente_id}).fetchone()
        return int(row[0]) if row else None

    def get_top_producto_categoria(self, categoria: str, excluir: list[str]) -> str | None:
        """Producto vigente más vendido (Venta Neta) de la `clase` dada, excluyendo los ya
        presentes en la canasta simulada -- fallback por popularidad de RN-CS1 cuando
        ningún producto de la canasta tiene una regla que cumpla `CROSS_SELL_MIN_LIFT`."""
        row = self.db.execute(text(
            """
            SELECT p.codart
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND p.producto_sk <> -1
              AND p.es_vigente AND p.clase = :categoria
              AND (:excluir = ARRAY[]::varchar[] OR NOT (p.codart = ANY(:excluir)))
            GROUP BY p.codart
            ORDER BY SUM(fvd.subtotal_neto) DESC
            LIMIT 1
            """
        ), {"categoria": categoria, "excluir": excluir}).fetchone()
        return str(row[0]) if row else None
