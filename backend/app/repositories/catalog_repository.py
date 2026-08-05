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

    def count_vendedores_activos(self) -> int:
        """Fase 5 §5.5 (dashboard de Admin, métricas reales): total real desde el EDW,
        excluye el centinela -1 (regla 12)."""
        row = self.db.execute(text(
            "SELECT COUNT(*) FROM edw.dim_vendedor WHERE vendedor_sk <> -1 AND activo"
        )).fetchone()
        return int(row[0]) if row else 0

    def count_almacenes(self) -> int:
        """Fase 5 §5.5: total real desde edw.dim_almacen, excluye el centinela -1."""
        row = self.db.execute(text(
            "SELECT COUNT(*) FROM edw.dim_almacen WHERE almacen_sk <> -1"
        )).fetchone()
        return int(row[0]) if row else 0

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
        docs/auditoria/25_modulo_cross_selling.md §2.5) -- solo catálogo vigente.
        Incluye `margen_unitario` (mismo criterio que `get_products_info`, H25-4:
        None sin costo derivable) para que el resumen de la canasta pueda estimar
        margen también de productos agregados por búsqueda directa, no solo de
        sugerencias."""
        like = f"%{query}%"
        rows = self.db.execute(text(
            """
            SELECT codart, nombre_articulo, clase, nombre_clase, precio_oficial, costo_promedio
            FROM edw.dim_producto
            WHERE es_vigente AND producto_sk <> -1
              AND (codart ILIKE :like OR nombre_articulo ILIKE :like)
            ORDER BY nombre_articulo
            LIMIT :limit
            """
        ), {"like": like, "limit": limit}).fetchall()
        resultado = []
        for r in rows:
            precio = float(r[4]) if r[4] is not None else 0.0
            costo = float(r[5]) if r[5] is not None else None
            resultado.append({
                "codart": str(r[0]), "nombre": r[1] or "",
                "categoria": r[3] or r[2] or "", "precio": precio,
                "margen_unitario": (precio - costo) if costo is not None and costo > 0 else None,
            })
        return resultado

    def search_vendedores(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Autocompletar vendedor por código SAP o nombre (config de Comisiones
        Variables -- pestaña "Tipo de vendedor"): una sola consulta ILIKE sobre
        `edw.dim_vendedor`, sin joins a fact, para no colapsar el backend con cada
        tecla escrita en el frontend (el caller debe debouncear/paginar con `limit`)."""
        like = f"%{query}%"
        rows = self.db.execute(text(
            """
            SELECT codven, nombre_vendedor
            FROM edw.dim_vendedor
            WHERE vendedor_sk <> -1 AND activo
              AND (codven ILIKE :like OR nombre_vendedor ILIKE :like)
            ORDER BY nombre_vendedor
            LIMIT :limit
            """
        ), {"like": like, "limit": limit}).fetchall()
        return [{"codven": str(r[0]), "nombre_vendedor": r[1]} for r in rows]

    def get_vendedores_activo_bulk(self, codvens: list[str]) -> dict[str, bool]:
        """Estado `activo` (edw.dim_vendedor.activo) para una lista conocida de códigos
        -- una sola consulta con `= ANY(...)`, mismo patrón de lote que
        `get_vendedores_info` (nunca N+1). Un `codven` que no resuelve en el EDW se
        considera inactivo (`False`) por defecto: nunca se asume activo sobre un dato
        ausente."""
        if not codvens:
            return {}
        rows = self.db.execute(text(
            "SELECT codven, activo FROM edw.dim_vendedor WHERE codven = ANY(:codvens)"
        ), {"codvens": codvens}).fetchall()
        encontrados = {str(r[0]): bool(r[1]) for r in rows}
        return {codven: encontrados.get(codven, False) for codven in codvens}

    def get_vendedores_info(self, codvens: list[str]) -> dict[str, str | None]:
        """Enriquecimiento por lote: `codven -> nombre_vendedor` para una lista ya
        conocida de códigos (ej. la tabla de configuración de comisiones por
        vendedor). Una sola consulta con `= ANY(...)`, nunca una consulta por fila
        (evita N+1) -- mismo patrón que `get_products_info`."""
        if not codvens:
            return {}
        rows = self.db.execute(text(
            "SELECT codven, nombre_vendedor FROM edw.dim_vendedor WHERE codven = ANY(:codvens)"
        ), {"codvens": codvens}).fetchall()
        return {str(r[0]): r[1] for r in rows}

    def search_clases_producto(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Autocompletar clase de producto (config de Comisiones Variables --
        Matriz de categorías): `edw.dim_producto.nombre_clase` está 100% vacío en el
        catálogo real (auditoría 30 H2), así que la búsqueda es solo por código de
        `clase`, agregando cuántos productos vigentes tiene cada una como contexto
        para que gerencia identifique la categoría sin adivinar. Una sola consulta
        agregada, sin joins a fact."""
        like = f"%{query}%"
        rows = self.db.execute(text(
            """
            SELECT clase, COUNT(*) AS productos
            FROM edw.dim_producto
            WHERE es_vigente AND producto_sk <> -1 AND clase IS NOT NULL AND clase <> ''
              AND clase ILIKE :like
            GROUP BY clase
            ORDER BY clase
            LIMIT :limit
            """
        ), {"like": like, "limit": limit}).fetchall()
        return [{"clase": str(r[0]), "productos": int(r[1])} for r in rows]

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

    def get_cliente_datos(self, cliente_id: str) -> dict[str, Any] | None:
        """Nombre (PII real, `public.cliente_lookup`) + ciudad (`edw.dim_cliente`
        vigente) de un cliente por id transaccional. Usado por el perfil de cliente
        360 del asistente de Venta Cruzada (Fase 1) -- una sola consulta, no dos
        round-trips separados para dos campos del mismo cliente."""
        row = self.db.execute(text(
            """
            SELECT l.nombre_cliente, c.ciudad
            FROM public.cliente_lookup l
            LEFT JOIN edw.dim_cliente c ON c.hash_anonimo = l.hash_anonimo AND c.es_vigente
            WHERE l.id_cliente_transaccional = :cliente_id
            """
        ), {"cliente_id": cliente_id}).fetchone()
        if not row:
            return None
        return {"nombre": row[0] or "", "ciudad": row[1]}

    def cliente_pertenece_a_vendedor(self, cliente_id: str, codven: str) -> bool:
        """Verifica que el vendedor `codven` le haya vendido alguna vez a `cliente_id`
        -- RLS de cartera (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V2): antes
        `churn-risk`/`recommendations`/`clientes/{id}/segmento` aceptaban cualquier
        `cliente_id` sin verificar que perteneciera a la cartera del vendedor
        autenticado, permitiendo consultar clientes ajenos."""
        row = self.db.execute(text("""
            SELECT 1
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
            JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            WHERE ve.codven = :codven AND l.id_cliente_transaccional = :cliente_id
            LIMIT 1
        """), {"codven": codven, "cliente_id": cliente_id}).fetchone()
        return row is not None

    def search_clientes(
        self, query: str, limit: int = 10, codven_restriccion: str | None = None,
    ) -> list[dict[str, Any]]:
        """Autocompletar cliente por cédula/RUC (`id_cliente_transaccional`) o nombre
        para el asistente de Venta Cruzada. El EDW (`edw.dim_cliente`) es la fuente
        oficial y ancla la consulta -- filtra vigencia SCD2 (`es_vigente`) y excluye el
        centinela `cliente_sk = -1` (regla de negocio 12, CLAUDE.md), igual que el resto
        del repositorio (ver `get_cliente_sk_vigente`). `id_cliente_transaccional` y
        `nombre_cliente` son PII REAL que solo puede vivir en `public.cliente_lookup`
        (aislada del EDW a propósito, regla de negocio 8) -- `edw.dim_cliente` solo tiene
        `hash_anonimo`, nunca texto plano, así que esos dos campos concretos deben salir
        de ahí; el join se hace sobre el EDW, no al revés.

        `codven_restriccion` (RLS de cartera, mismo criterio que
        `cliente_pertenece_a_vendedor`/`_verificar_pertenencia_cartera`): si el llamador
        es un vendedor (rol `ventas`, sin override), el autocompletar solo debe ofrecer
        clientes a los que ESE vendedor le haya vendido alguna vez -- antes esta función
        buscaba en TODO el catálogo de clientes sin importar quién preguntara, así que
        cualquier vendedor podía encontrar y luego consultar (vía los demás endpoints,
        que sí validan pertenencia) el perfil/riesgo de churn/recomendaciones de un
        cliente ajeno con solo teclear su nombre. Gerencia/administrador pasan `None` y
        siguen viendo el catálogo completo.

        Enriquecida (Fase 1, docs/features/plan_refactor_venta_cruzada_ia.md CAMBIO 1):
        `ciudad` (`dim_cliente`, sin dimensión geográfica separada -- `dim_geografia`
        está vacía, hallazgo abierto de la auditoría 05), y `ultima_compra`/
        `frecuencia_12m`/`n_compras` calculados en una CTE aparte que agrega
        `fact_ventas_detalle` SOLO para los candidatos ya acotados por el `LIMIT` del
        autocompletar (nunca sobre todo el catálogo de clientes) -- sigue siendo una
        consulta barata apta para dispararse en cada tecla. Sin modelos ML: el
        autocompletar no puede esperar una inferencia."""
        like = f"%{query}%"
        params: dict[str, Any] = {"like": like, "limit": limit}
        filtro_cartera = ""
        if codven_restriccion is not None:
            filtro_cartera = """
                  AND EXISTS (
                      SELECT 1 FROM edw.fact_ventas_detalle fv
                      JOIN edw.dim_vendedor v ON fv.vendedor_sk = v.vendedor_sk
                      WHERE fv.cliente_sk = c.cliente_sk AND v.codven = :codven_restriccion
                  )
            """
            params["codven_restriccion"] = codven_restriccion
        rows = self.db.execute(text(
            f"""
            WITH candidatos AS (
                SELECT c.cliente_sk, l.id_cliente_transaccional, l.nombre_cliente, c.ciudad
                FROM edw.dim_cliente c
                JOIN public.cliente_lookup l ON l.hash_anonimo = c.hash_anonimo
                WHERE c.es_vigente AND c.cliente_sk <> -1
                  AND (l.id_cliente_transaccional ILIKE :like OR l.nombre_cliente ILIKE :like)
                  {filtro_cartera}
                ORDER BY l.nombre_cliente
                LIMIT :limit
            ),
            historial AS (
                SELECT
                    fvd.cliente_sk,
                    MAX(d.fecha_completa) AS ultima_compra,
                    COUNT(DISTINCT fvd.num_factura) FILTER (
                        WHERE d.fecha_completa >= CURRENT_DATE - INTERVAL '365 days'
                    ) AS frecuencia_12m,
                    COUNT(DISTINCT fvd.num_factura) AS n_compras
                FROM edw.fact_ventas_detalle fvd
                JOIN edw.dim_fecha d ON fvd.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
                  AND fvd.cliente_sk IN (SELECT cliente_sk FROM candidatos)
                GROUP BY fvd.cliente_sk
            )
            SELECT
                c.id_cliente_transaccional, c.nombre_cliente, c.ciudad,
                h.ultima_compra, h.frecuencia_12m, h.n_compras
            FROM candidatos c
            LEFT JOIN historial h ON h.cliente_sk = c.cliente_sk
            ORDER BY c.nombre_cliente
            """
        ), params).fetchall()
        return [
            {
                "cliente_id": str(r[0]), "nombre": r[1] or "", "ciudad": r[2],
                "ultima_compra": r[3], "frecuencia_12m": int(r[4]) if r[4] is not None else None,
                "n_compras": int(r[5]) if r[5] is not None else None,
            }
            for r in rows
        ]

    def get_top_productos_diversos(
        self, categorias_excluir: list[str], excluir_codarts: list[str], limit: int, min_productos_categoria: int = 5,
    ) -> list[dict[str, Any]]:
        """Top-1 producto más vendido de cada categoría DISTINTA a `categorias_excluir`
        (una fila por categoría, la mejor vendida de esa categoría), devolviendo las
        `limit` categorías con mayor venta. RN-CS3: usado para inyectar diversidad real
        entre categorías cuando el artefacto item-item no la provee -- algunos productos
        (p.ej. baterías) tienen sus 20 vecinos entrenados TODOS en la misma categoría
        (hallazgo de uso real, auditoría 25 §6.1); sin esto, el asistente nunca podría
        ofrecer venta cruzada real entre categorías para esos productos.

        `min_productos_categoria` excluye categorías-cajón/mal clasificadas (`clase`
        vacía o con un puñado de artículos, p.ej. 'Z-999' con 1 solo producto
        "BATERIAS CHATARRAS" -- hallazgo real durante la verificación de esta regla):
        sin este filtro, la categoría con un único artículo aparece siempre como su
        propio "top-1", devolviendo chatarra/residuos como sugerencia de venta cruzada."""
        rows = self.db.execute(text(
            """
            SELECT codart, categoria, venta FROM (
                SELECT
                    p.codart, p.clase AS categoria, SUM(fvd.subtotal_neto) AS venta,
                    ROW_NUMBER() OVER (PARTITION BY p.clase ORDER BY SUM(fvd.subtotal_neto) DESC) AS rn
                FROM edw.fact_ventas_detalle fvd
                JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND p.producto_sk <> -1
                  AND p.es_vigente AND p.clase IS NOT NULL AND p.clase <> ''
                  AND NOT (p.clase = ANY(:categorias_excluir))
                  AND NOT (p.codart = ANY(:excluir_codarts))
                  AND p.clase IN (
                      SELECT clase FROM edw.dim_producto
                      WHERE es_vigente AND producto_sk <> -1 AND clase IS NOT NULL AND clase <> ''
                      GROUP BY clase HAVING count(*) >= :min_productos_categoria
                  )
                GROUP BY p.clase, p.codart
            ) ranked
            WHERE rn = 1
            ORDER BY venta DESC
            LIMIT :limit
            """
        ), {
            "categorias_excluir": categorias_excluir, "excluir_codarts": excluir_codarts,
            "limit": limit, "min_productos_categoria": min_productos_categoria,
        }).fetchall()
        return [{"codart": str(r[0]), "categoria": r[1]} for r in rows]

    def get_top_combinaciones(self, limit: int = 3, dias: int = 730) -> list[dict[str, Any]]:
        """Parejas de productos con mayor co-ocurrencia histórica en facturas válidas
        dentro de los últimos `dias` (docs/auditoria/25_modulo_cross_selling.md §6.4):
        KPI que no depende de la telemetría del asistente (siempre tiene datos, ya que
        se calcula directo sobre `fact_ventas_detalle`) y le da al vendedor un ejemplo
        concreto y ya validado de qué ofrecer junto a qué. Mismas exclusiones que el
        resto del repositorio: estado válido, sin devoluciones, catálogo vigente
        (regla 12 CLAUDE.md)."""
        rows = self.db.execute(text(
            """
            SELECT p1.codart, p1.nombre_articulo, p2.codart, p2.nombre_articulo,
                   COUNT(DISTINCT f1.num_factura) AS facturas
            FROM edw.fact_ventas_detalle f1
            JOIN edw.fact_ventas_detalle f2
              ON f1.num_factura = f2.num_factura AND f1.producto_sk < f2.producto_sk
            JOIN edw.dim_producto p1 ON f1.producto_sk = p1.producto_sk
            JOIN edw.dim_producto p2 ON f2.producto_sk = p2.producto_sk
            JOIN edw.dim_estado_documento ed ON f1.estado_documento_sk = ed.estado_documento_sk
            JOIN edw.dim_fecha d ON f1.fecha_sk = d.fecha_sk
            WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
              AND p1.producto_sk <> -1 AND p2.producto_sk <> -1
              AND p1.es_vigente AND p2.es_vigente
              AND d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
            GROUP BY p1.codart, p1.nombre_articulo, p2.codart, p2.nombre_articulo
            ORDER BY facturas DESC
            LIMIT :limit
            """
        ), {"dias": dias, "limit": limit}).fetchall()
        return [
            {
                "codart_a": str(r[0]), "nombre_a": r[1] or "",
                "codart_b": str(r[2]), "nombre_b": r[3] or "",
                "facturas": int(r[4]),
            }
            for r in rows
        ]

    def get_top_margen_relativo(self, limit: int = 4, min_productos_categoria: int = 5) -> list[dict[str, Any]]:
        """Top-1 producto por CATEGORÍA con mayor margen relativo `(precio-costo)/precio`
        (una fila por categoría, para el combo "Mayor Rentabilidad" de la Fase 4,
        docs/features/plan_refactor_venta_cruzada_ia.md) -- mismo patrón de diversidad
        que `get_top_productos_diversos` (RN-CS3), para no devolver 4 variantes casi
        idénticas de la misma categoría. Solo catálogo vigente CON costo real
        (`costo_promedio > 0`, H25-4: nunca se inventa margen) y con al menos una venta
        histórica real (excluye SKUs sin movimiento, que inflarían el ranking con
        combinaciones de precio/costo nunca puestas a prueba en el mercado)."""
        rows = self.db.execute(text(
            """
            SELECT codart, nombre_articulo, clase, precio_oficial, costo_promedio, margen_relativo
            FROM (
                SELECT
                    p.codart, p.nombre_articulo, p.clase, p.precio_oficial, p.costo_promedio,
                    (p.precio_oficial - p.costo_promedio) / p.precio_oficial AS margen_relativo,
                    ROW_NUMBER() OVER (PARTITION BY p.clase ORDER BY (p.precio_oficial - p.costo_promedio) / p.precio_oficial DESC) AS rn
                FROM edw.dim_producto p
                WHERE p.es_vigente AND p.producto_sk <> -1
                  AND p.costo_promedio IS NOT NULL AND p.costo_promedio > 0 AND p.precio_oficial > 0
                  AND p.clase IS NOT NULL AND p.clase <> ''
                  AND p.clase IN (
                      SELECT clase FROM edw.dim_producto
                      WHERE es_vigente AND producto_sk <> -1 AND clase IS NOT NULL AND clase <> ''
                      GROUP BY clase HAVING count(*) >= :min_productos_categoria
                  )
                  AND EXISTS (
                      SELECT 1 FROM edw.fact_ventas_detalle f
                      JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                      WHERE f.producto_sk = p.producto_sk AND ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
                  )
            ) ranked
            WHERE rn = 1
            ORDER BY margen_relativo DESC
            LIMIT :limit
            """
        ), {"limit": limit, "min_productos_categoria": min_productos_categoria}).fetchall()
        return [
            {
                "codart": str(r[0]), "nombre": r[1] or "", "categoria": r[2] or "",
                "precio": float(r[3]), "margen_unitario": float(r[3]) - float(r[4]),
            }
            for r in rows
        ]

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
              AND NOT (p.codart = ANY(:excluir))
            GROUP BY p.codart
            ORDER BY SUM(fvd.subtotal_neto) DESC
            LIMIT 1
            """
        ), {"categoria": categoria, "excluir": excluir}).fetchone()
        return str(row[0]) if row else None
