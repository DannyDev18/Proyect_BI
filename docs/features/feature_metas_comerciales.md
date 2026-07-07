# Especificación de Diseño: Automatización de Metas Comerciales y Comisiones Inteligentes

Esta guía documenta la arquitectura técnica, modelo de datos, servicios de backend en FastAPI y estructura del frontend en React para implementar la automatización de metas comerciales con aprobación del Gerente y liquidación de comisiones.

---

## 1. FLUJO GENERAL DEL PROCESO

El flujo de trabajo automatizado se divide en cuatro fases cíclicas mensuales:

```
  [1. Predicción / ETL] ──> [2. Propuesta Inicial] ──> [3. Aprobación Gerente]
                                                               │
  [5. Liquidación] <─────── [4. Monitoreo Tiempo Real] <────────┘
```

1. **Predicción y Generación (ETL/ML):** El primer día de cada mes, se ejecuta una rutina en segundo plano que analiza el historial de ventas reales del vendedor/sucursal del mes anterior. Mediante IA/Regresión o factores de crecimiento históricos, el sistema genera metas mensuales sugeridas y las registra con estado `PROPUESTA`.
2. **Revisión y Ajuste Gerencial:** El Gerente accede a su consola en React, revisa los borradores sugeridos en una tabla interactiva, modifica manualmente las metas que considere necesarias y las aprueba (`APROBADA`).
3. **Monitoreo en Tiempo Real (Presión Comercial):** Con las metas activadas, el dashboard del Vendedor y de la Sucursal calcula de forma continua el porcentaje de logro diario. El termómetro visual (semáforo) alerta al vendedor sobre su estado en relación a la meta comercial.
4. **Cierre de Ciclo y Liquidación:** Al final del mes, se ejecuta el reporte de comisiones. Las comisiones se liquidan automáticamente a partir de reglas escalonadas, listas para exportarse directamente a los sistemas de nómina.

---

## 2. ESQUEMA DE BASE DE DATOS (PostgreSQL 16)

Siguiendo las mejores prácticas de diseño de base de datos para PostgreSQL (sustitución de tipos antiguos como `SERIAL` por `GENERATED ALWAYS AS IDENTITY`, uso de `TEXT` con restricciones en lugar de `VARCHAR` no acotados y agregando índices explícitos sobre todas las llaves foráneas):

```sql
-- Creación de la tabla de metas comerciales operativas
CREATE TABLE IF NOT EXISTS public.metas_comerciales_operativas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    anio INT NOT NULL CHECK (anio >= 2020),
    mes INT NOT NULL CHECK (mes BETWEEN 1 AND 12),

    -- Codigo natural de vendedor referenciando a la tabla usuarios
    id_vendedor_origen TEXT REFERENCES public.usuarios(id_vendedor_origen) ON DELETE SET NULL,
    sucursal TEXT NOT NULL CHECK (length(sucursal) <= 100),

    monto_meta NUMERIC(15,4) NOT NULL DEFAULT 0.0000 CHECK (monto_meta >= 0),
    unidades_meta NUMERIC(15,4) NOT NULL DEFAULT 0.0000 CHECK (unidades_meta >= 0),
    comision_base_pct NUMERIC(5,2) NOT NULL DEFAULT 2.00 CHECK (comision_base_pct BETWEEN 0 AND 100),
    bono_sobrecumplimiento NUMERIC(15,4) NOT NULL DEFAULT 100.0000 CHECK (bono_sobrecumplimiento >= 0),

    estado TEXT NOT NULL DEFAULT 'PROPUESTA' CHECK (estado IN ('PROPUESTA', 'APROBADA', 'RECHAZADA')),
    approved_by INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,

    -- Timestamps con zona horaria incorporada por estandar de auditoria
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (anio, mes, id_vendedor_origen, sucursal)
);

-- Indices para queries de filtrado y optimizacion de agregaciones
CREATE INDEX IF NOT EXISTS idx_metas_anio_mes ON public.metas_comerciales_operativas(anio, mes);
CREATE UNIQUE INDEX IF NOT EXISTS idx_metas_vendedor_key ON public.metas_comerciales_operativas(id_vendedor_origen) WHERE id_vendedor_origen IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metas_estado ON public.metas_comerciales_operativas(estado);

-- FK INDEX (Crucial para optimizar eliminaciones en tablas padres y evitar table locks)
CREATE INDEX IF NOT EXISTS idx_metas_approved_by ON public.metas_comerciales_operativas(approved_by);
```

---

## 3. IMPLEMENTACIÓN EN EL BACKEND (FastAPI & SQLAlchemy)

### Esquemas de Validacion de Datos (Pydantic V2)

Definimos los modelos estrictamente tipados para garantizar la integridad en las firmas de entrada y salida:

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class GoalProposalCreate(BaseModel):
    anio: int = Field(..., ge=2020, description="Año correspondiente a la meta")
    mes: int = Field(..., ge=1, le=12, description="Mes correspondiente")
    id_vendedor_origen: Optional[str] = Field(None, max_length=15)
    sucursal: str = Field(..., min_length=2, max_length=100)
    monto_meta: float = Field(..., ge=0.0)
    unidades_meta: float = Field(..., ge=0.0)

class GoalReviewPayload(BaseModel):
    monto_meta: Optional[float] = Field(None, ge=0.0)
    estado: str = Field(..., pattern="^(APROBADA|RECHAZADA)$")
    comision_base_pct: Optional[float] = Field(None, ge=0.0, le=100.0)

class GoalCommissionReportItem(BaseModel):
    vendedor: str
    sucursal: str
    meta_monto: float
    venta_real: float
    progreso_pct: float
    comision_variable: float
    bono_aplicado: float
    total_liquidacion: float
```

### Capa de Servicio Asíncrona: `backend/app/services/analytics_service.py`

Implementación asíncrona optimizada para concurrencia mediante SQLAlchemy 2.0 y prevención de fugas de datos:

```python
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GoalsAutomationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generar_propuestas_metas(self, anio: int, mes: int, factor_presion: float = 1.10) -> int:
        """
        Extrapola las ventas del periodo anterior y genera propuestas de metas comerciales
        """
        mes_ant = 12 if mes == 1 else mes - 1
        anio_ant = anio - 1 if mes == 1 else anio

        query_historial = text("""
            SELECT
                v.codven AS vendedor_origen,
                s.nombre_sucursal AS sucursal,
                SUM(f.subtotal_neto) AS ventas_anterior,
                SUM(f.cantidad) AS unidades_anterior
            FROM edw.fact_ventas_detail f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            WHERE d.anio = :anio_ant AND d.mes = :mes_ant AND f.estado_factura != 'I'
            GROUP BY v.codven, s.nombre_sucursal
        """)

        try:
            result = await self.db.execute(query_historial, {"anio_ant": anio_ant, "mes_ant": mes_ant})
            historial = result.fetchall()
            registros_creados = 0

            for row in historial:
                cod_ven, sucursal, ventas_ant, unidades_ant = row
                meta_monto = float(ventas_ant or 0.0) * factor_presion
                meta_unidades = float(unidades_ant or 0.0) * factor_presion

                query_insert = text("""
                    INSERT INTO public.metas_comerciales_operativas
                    (anio, mes, id_vendedor_origen, sucursal, monto_meta, unidades_meta, estado)
                    VALUES (:anio, :mes, :vendedor, :sucursal, :meta_monto, :meta_unidades, 'PROPUESTA')
                    ON CONFLICT (anio, mes, id_vendedor_origen, sucursal)
                    DO NOTHING;
                """)
                await self.db.execute(query_insert, {
                    "anio": anio, "mes": mes, "vendedor": cod_ven, "sucursal": sucursal,
                    "meta_monto": meta_monto, "meta_unidades": meta_unidades
                })
                registros_creados += 1

            await self.db.commit()
            return registros_creados
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error generando metas automáticas: {str(e)}")
            raise e

    async def liquidar_comisiones_periodo(self, anio: int, mes: int) -> List[Dict[str, Any]]:
        """
        Calcula las comisiones liquidadas basándose en la consecución de las metas.
        """
        query = text("""
            SELECT
                u.nombre AS vendedor,
                m.sucursal,
                m.monto_meta AS meta_monto,
                COALESCE(SUM(f.subtotal_neto), 0) AS venta_real,
                m.comision_base_pct,
                m.bono_sobrecumplimiento
            FROM public.metas_comerciales_operativas m
            JOIN public.usuarios u ON m.id_vendedor_origen = u.id_vendedor_origen
            LEFT JOIN edw.dim_vendedor dv ON u.id_vendedor_origen = dv.codven
            LEFT JOIN edw.fact_ventas_detail f ON dv.vendedor_sk = f.vendedor_sk
            LEFT JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk AND d.anio = m.anio AND d.mes = m.mes
            WHERE m.anio = :anio AND m.mes = :mes AND m.estado = 'APROBADA'
            GROUP BY u.nombre, m.sucursal, m.monto_meta, m.comision_base_pct, m.bono_sobrecumplimiento
        """)

        result = await self.db.execute(query, {"anio": anio, "mes": mes})
        datos = result.fetchall()
        reporte = []

        for row in datos:
            vendedor, sucursal, meta, realizada, com_pct, bono = row
            meta_val = float(meta)
            real_val = float(realizada)
            com_pct_val = float(com_pct)
            bono_val = float(bono)

            progreso_pct = (real_val / meta_val) * 100 if meta_val > 0 else 0.0

            comision_generada = 0.0
            bono_pagado = 0.0
            if progreso_pct >= 80.0:
                comision_generada = real_val * (com_pct_val / 100.0)
                if progreso_pct >= 100.0:
                    bono_pagado = bono_val

            reporte.append({
                "vendedor": vendedor,
                "sucursal": sucursal,
                "meta": round(meta_val, 2),
                "acumulado_ventas": round(real_val, 2),
                "progreso_pct": round(progreso_pct, 2),
                "comision_variable": round(comision_generada, 2),
                "bono_aplicado": round(bono_pagado, 2),
                "monto_total_liquidacion": round(comision_generada + bono_pagado, 2)
            })

        return reporte
```

---

## 4. INTERFAZ DE FRONTEND (React 19 & Tailwind CSS)

Aplicando las reglas del manual UI/UX Pro Max:

- **Sin emojis para iconos:** Se utiliza `<Lucide />` de forma integral.
- **Acción Asíncrona Adaptativa:** Se inhabilitan los botones y se muestran estados de carga (`loading`) para prevenir clicks duplicados.
- **Interactividad Acelerada:** Transiciones suaves de 200ms para todos los botones e interacciones.
- **Cursor de Navegación:** Indicador manual `cursor-pointer` en todos los inputs, selectores y controles deslizantes.

```tsx
import React, { useState, useEffect } from "react";
import {
  CheckCircle,
  XCircle,
  TrendingUp,
  Trophy,
  AlertTriangle,
  Loader2,
} from "lucide-react";

interface GoalProposal {
  id: number;
  vendedor: string;
  sucursal: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
}

export function GoalsConsole() {
  const [proposals, setProposals] = useState<GoalProposal[]>([]);
  const [pressure, setPressure] = useState<number>(10);
  const [period, setPeriod] = useState({ anio: 2026, mes: 7 });
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  useEffect(() => {
    fetchProposals();
  }, [period]);

  const fetchProposals = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/gerencia/goals/tracking?anio=${period.anio}&mes=${period.mes}`,
      );
      const data = await res.json();
      setProposals(data.reporte_cumplimiento || []);
    } catch (err) {
      console.error("Error cargando metas:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    const factor = 1 + pressure / 100;
    try {
      await fetch(
        `/api/v1/gerencia/goals/generate?anio=${period.anio}&mes=${period.mes}&pressure_factor=${factor}`,
        {
          method: "POST",
        },
      );
      await fetchProposals();
    } catch (err) {
      console.error("Error generando metas:", err);
      setLoading(false);
    }
  };

  const handleReview = async (
    id: number,
    estado: "APROBADA" | "RECHAZADA",
    monto: number,
    comision: number,
  ) => {
    setActionLoadingId(id);
    try {
      await fetch(`/api/v1/gerencia/goals/${id}/review`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          monto_meta: monto,
          estado: estado,
          comision_base_pct: comision,
        }),
      });
      await fetchProposals();
    } catch (err) {
      console.error("Error procesando aprobacion:", err);
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Trophy className="w-8 h-8 text-teal-400" />
        <h2 className="text-2xl font-bold tracking-tight">
          Consola Inteligente de Metas & Comisiones
        </h2>
      </div>

      {/* Panel de Configuración Automática con Cursors definidos */}
      <div className="p-5 bg-slate-850 rounded-lg mb-6 flex flex-wrap gap-6 items-center border border-slate-750">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400">
            Año / Mes de Planificación
          </label>
          <select
            className="bg-slate-800 p-2 rounded text-sm border border-slate-700 cursor-pointer focus:border-teal-400 focus:outline-none transition-colors"
            onChange={(e) =>
              setPeriod({ ...period, mes: parseInt(e.target.value) })
            }
            value={period.mes}
            disabled={loading}
          >
            <option value={7}>Julio 2026</option>
            <option value={8}>Agosto 2026</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px] flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400">
            Factor de Presión Comercial (+{pressure}%)
          </label>
          <input
            type="range"
            min="0"
            max="25"
            value={pressure}
            disabled={loading}
            onChange={(e) => setPressure(parseInt(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-400"
          />
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="bg-teal-500 hover:bg-teal-400 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold py-2.5 px-5 rounded text-sm transition-all duration-200 ease-in-out cursor-pointer flex items-center gap-2"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <TrendingUp className="w-4 h-4" />
          )}
          Generar Plan con Inteligencia ML
        </button>
      </div>

      {/* Grilla Interactiva */}
      <div className="bg-slate-850 rounded-lg p-5 border border-slate-750">
        <h3 className="text-lg font-semibold mb-4 text-slate-200">
          Revisión de Flujo y Propuestas
        </h3>

        {loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-10 h-10 animate-spin text-teal-400" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-750 text-slate-400 font-medium">
                  <th className="p-3">Vendedor</th>
                  <th className="p-3">Sucursal</th>
                  <th className="p-3">Meta Propuesta ($)</th>
                  <th className="p-3">Comisión (%)</th>
                  <th className="p-3">Estado</th>
                  <th className="p-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-slate-800 hover:bg-slate-800/50 transition-all duration-150"
                  >
                    <td className="p-3 font-semibold text-teal-50">
                      {p.vendedor}
                    </td>
                    <td className="p-3 text-slate-300">{p.sucursal}</td>
                    <td className="p-3">
                      <input
                        type="number"
                        defaultValue={p.monto_meta}
                        onBlur={(e) =>
                          (p.monto_meta = parseFloat(e.target.value))
                        }
                        className="bg-slate-800 w-28 p-1.5 rounded border border-slate-700 focus:outline-none focus:border-teal-400 transition-colors cursor-text"
                      />
                    </td>
                    <td className="p-3">
                      <input
                        type="number"
                        defaultValue={p.comision_base_pct}
                        onBlur={(e) =>
                          (p.comision_base_pct = parseFloat(e.target.value))
                        }
                        className="bg-slate-800 w-16 p-1.5 rounded border border-slate-700 focus:outline-none focus:border-teal-400 transition-colors cursor-text"
                      />
                    </td>
                    <td className="p-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                          p.estado === "APROBADA"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                            : "bg-amber-500/10 text-amber-400 border border-amber-500/25"
                        }`}
                      >
                        {p.estado === "APROBADA" ? (
                          <CheckCircle className="w-3.5 h-3.5" />
                        ) : (
                          <AlertTriangle className="w-3.5 h-3.5" />
                        )}
                        {p.estado}
                      </span>
                    </td>
                    <td className="p-3 text-right flex justify-end gap-2">
                      <button
                        onClick={() =>
                          handleReview(
                            p.id,
                            "APROBADA",
                            p.monto_meta,
                            p.comision_base_pct,
                          )
                        }
                        disabled={actionLoadingId === p.id}
                        className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold py-1.5 px-3 rounded text-xs transition-colors duration-200 cursor-pointer flex items-center gap-1"
                      >
                        {actionLoadingId === p.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : null}
                        Aprobar
                      </button>
                      <button
                        onClick={() =>
                          handleReview(
                            p.id,
                            "RECHAZADA",
                            p.monto_meta,
                            p.comision_base_pct,
                          )
                        }
                        disabled={actionLoadingId === p.id}
                        className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-semibold py-1.5 px-3 rounded text-xs transition-colors duration-200 cursor-pointer flex items-center gap-1"
                      >
                        {actionLoadingId === p.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : null}
                        Rechazar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

---

## 5. MÉTODOS DE CONTROL Y SEGUIMIENTO (PRESIÓN VISUAL)

Para "meter presión" de forma gamificada sobre los vendedores en el Frontend, utiliza los siguientes indicadores calculados:

| Avance Real (%)          | Color Visual                  | Etiqueta en UI           | Penalización/Incentivo                                                  |
| :----------------------- | :---------------------------- | :----------------------- | :---------------------------------------------------------------------- |
| **Menos del 80%**        | Rojo (`bg-rose-500`)          | Alerta: Meta Crítica     | **Penalización:** Sin comisión sobre ventas en el periodo.              |
| **80% a 99.9%**          | Naranja (`bg-amber-500`)      | Meta Cerca / En Progreso | **Base:** Comisión proporcional según `comision_base_pct`.              |
| **Mayor o igual a 100%** | Verde Glow (`bg-emerald-500`) | Logrado / Exitoso        | **Bono extra:** Recibe suma fija adicional de `bono_sobrecumplimiento`. |
