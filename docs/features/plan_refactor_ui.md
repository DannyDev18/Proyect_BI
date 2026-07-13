# Plan de refactorización UI/UX — "Signal Deck 2.0"

> **Fecha:** 2026-07-12
> **Alcance:** `frontend/` completo (shell, primitivas UI, 13 páginas, gráficos Recharts).
> **Estado:** PLAN — pendiente de aprobación antes de implementar.
> **Relación:** complementa `plan_prediccion_categoria_paginacion.md` (el componente
> `Pagination`/`DataTable` de este plan es el que consumen las tablas paginadas de aquel).

---

## 1. Diagnóstico del estado actual (verificado en código)

El frontend **no parte de cero**: existe un sistema de diseño con identidad propia,
"Signal Deck" ([index.css](../../frontend/src/index.css)) — consola oscura tipo panel
de instrumentos con tres decisiones fuertes ya tomadas:

1. **Tipografía con carácter:** Fraunces (serif editorial) reservada a los H1,
   IBM Plex Sans para cuerpo, JetBrains Mono para cifras.
2. **Semántica de procedencia del dato:** cian = dato real del EDW, ámbar =
   predicción de modelo ML (badges en `ChartCard`, `ProvenanceRail` en el layout).
   Esta es la firma visual del producto y **se conserva y amplifica**.
3. Tokens de color en `@theme`, skeletons con shimmer, `prefers-reduced-motion`
   ya respetado.

El problema no es la ausencia de sistema sino su **aplicación inconsistente y su
cobertura incompleta**. Lo que hace que el sistema se sienta "básico":

| # | Problema | Evidencia |
|---|---|---|
| P1 | Colores hardcodeados fuera de los tokens | `DashboardBodega.tsx` define su propia paleta hex (`#2563EB`, `#F59E0B`…), `tooltipStyle` inline con hex repetido en cada página; los `ReferenceLine`, ejes y grids de Recharts usan hex sueltos. |
| P2 | Solo 6 primitivas UI | `KpiCard`, `ChartCard`, `AlertBadge`, `LoadingSpinner`, `SearchInput`, `GlobalBranchSelector`. No hay `Table`, `Button`, `Select`, `Tabs`, `Modal/Drawer`, `Toast`, `EmptyState` — cada página improvisa los suyos con clases crudas (los `<select>` y tablas de `DashboardBodega` son HTML plano estilizado ad-hoc). |
| P3 | Motion plano | Solo `fade-in`/`fade-in-up` con stagger manual (`animDelay` numérico pasado a mano). No hay transición entre rutas, ni count-up en KPIs, ni entrada de gráficos, ni micro-interacciones más allá de `hover:border`. |
| P4 | Estados incompletos | Loading tiene skeletons, pero vacío y error son un `<td colSpan>` o un div rojo distintos en cada página; sin retry visible ni ilustración/acción. |
| P5 | Jerarquía visual débil en tablas | Tablas largas con scroll interno (`max-h + overflow`), sin densidad configurable, sin sticky mejorado, sin resaltado de fila crítica sistemático. |
| P6 | Accesibilidad parcial | Sin `focus-visible` consistente, contraste `text-slate-500` sobre `slate-900` roza el límite AA en textos pequeños, selects nativos sin estilo de foco. |

**Decisión de diseño rectora:** no se reemplaza la identidad — se ejecuta con
disciplina. La audacia ya está gastada donde debe (Fraunces + semántica de
procedencia); este refactor invierte en precisión: tokens sin fugas, primitivas
completas, motion orquestado y estados de UX de calidad producto.

## 2. Sistema de diseño consolidado (tokens)

### 2.1 Color — cerrar las fugas

Todo color visible sale de `@theme`; se **prohíbe hex inline** en páginas (regla
verificable con grep en la validación).

Nuevos tokens a agregar en `index.css`:

```css
/* Paleta categórica para gráficos (hoy hardcodeada en DashboardBodega) */
--color-chart-1..8            /* derivada de la actual CATEGORY_COLORS, contrastada sobre bg-surface */
/* Recharts chrome */
--color-chart-grid            /* hoy #1e293b inline */
--color-chart-axis            /* hoy #64748b inline */
/* Elevaciones y foco */
--color-bg-overlay            /* modales/drawers */
--ring-focus                  /* anillo de foco accesible, cian al 60% */
```

### 2.2 Motion — tokens y orquestación

```css
--ease-out-soft: cubic-bezier(0.16, 1, 0.3, 1);   /* entradas */
--ease-in-out-panel: cubic-bezier(0.4, 0, 0.2, 1); /* drawers/acordeones */
--duration-fast: 150ms;   /* micro-interacciones: hover, focus, toggle */
--duration-base: 300ms;   /* entradas de tarjetas, tabs */
--duration-slow: 500ms;   /* transición de ruta, drawer */
```

Principio: **una secuencia orquestada por página** (header → KPIs en stagger →
gráficos), no efectos dispersos. El stagger deja de ser `animDelay` manual: utilidad
CSS `stagger-children` en el contenedor (`animation-delay` por `:nth-child`), con lo
que las páginas dejan de calcular retardos a mano.

`prefers-reduced-motion` se mantiene y se extiende a todas las animaciones nuevas
(las utilidades nuevas entran al mismo bloque `@media` existente).

### 2.3 Tipo y espaciado

- Escala tipográfica documentada (hoy implícita): H1 `text-3xl font-display`,
  título de card `text-base font-semibold`, eyebrow `text-xs uppercase
  tracking-widest`, cifra `font-mono text-3xl`. Sin cambios de fuentes — solo se
  fija por escrito para que las páginas nuevas no inventen.
- Espaciado vertical de página unificado: `space-y-6` entre secciones (ya es el
  patrón dominante), `p-6` interior de cards.

## 3. Biblioteca de componentes (P2, P4, P5)

Nuevos en `frontend/src/components/ui/`, todos tipados, con la misma estética de
panel plano + hairline:

| Componente | Qué resuelve | Notas de diseño |
|---|---|---|
| `Button.tsx` | Botones improvisados con clases crudas en cada página | Variantes `primary` (cian sólido), `ghost` (borde hairline), `danger`; estados hover/active/disabled/loading (spinner embebido); `focus-visible:ring`. |
| `Select.tsx` | `<select>` nativos sin identidad | Wrapper estilizado del nativo (sin librería): chevron lucide, foco accesible, tamaño `sm` para toolbars de gráfico. |
| `DataTable.tsx` | Tablas ad-hoc (P5) | Cabecera sticky, columnas tipadas, densidad `normal/compact`, fila crítica con tinte `danger-dim`, celdas numéricas `font-mono` alineadas a la derecha, ordenamiento visual por columna, y slot de `<Pagination>` (plan de paginación). Estados loading (skeleton de filas), empty y error integrados. |
| `Pagination.tsx` | (compartido con el plan de paginación) | « ‹ pág › » + "X–Y de Z" + tamaño de página. |
| `EmptyState.tsx` | Vacíos como filas grises (P4) | Icono lucide + mensaje + acción sugerida ("Limpiar filtros"); registro en voz de producto: dice qué hacer, no solo que no hay datos. |
| `ErrorState.tsx` | Errores como texto rojo suelto | Mensaje claro + botón "Reintentar" (usa el `refetch` que los hooks ya exponen). |
| `Toast.tsx` + `useToast` | Sin feedback de acciones (descargas Excel, guardados en Settings/Users) | Esquina inferior derecha, entrada `fade-in-up`, auto-dismiss, variantes success/error. |
| `Drawer.tsx` | Detalle sin salir del dashboard (drill-down de artículo, detalle de transferencia) | Panel lateral derecho sobre `bg-overlay` con blur, entrada `--duration-slow`; cierra con Esc y clic fuera; focus trap. |
| `Tabs.tsx` | Vistas alternas dentro de una card (ej. "Recomendados / No comprar" en G6) | Subrayado animado deslizante (indicador que se mueve, no que reaparece). |
| `CountUp.tsx` | Cifras de KPI que aparecen secas | Animación numérica ~600ms con `--ease-out-soft` al montar/cambiar; desactivada bajo reduced-motion (muestra el valor final directo). |
| `ChartTooltip.tsx` + `chartTheme.ts` | `tooltipStyle` duplicado en cada página (P1) | Tooltip único de Recharts (panel elevated + hairline) y objeto `chartTheme` con grid/ejes/paleta desde tokens, importado por todos los gráficos. |

**Componentes existentes — mejoras puntuales:**

- `KpiCard`: integra `CountUp`; micro-interacción hover (el icono adopta
  `glow-accent-sm`); el trend usa flechas lucide en lugar de caracteres de texto.
- `ChartCard`: acepta `empty`/`error` (renderiza `EmptyState`/`ErrorState` dentro
  del área del gráfico, elimina los ternarios repetidos de las páginas).
- `Sidebar`: indicador de ruta activa animado (barra cian que se desliza entre
  ítems), tooltips en modo colapsado.
- `Header`/`NotificationBell`: dropdown con entrada animada y focus trap.

## 4. Motion por superficie (P3)

| Superficie | Animación | Duración |
|---|---|---|
| Cambio de ruta | Fade + translateY(8px) del contenido de `<Outlet>` (wrapper en `Layout.tsx`, sin librería de router-transitions) | `--duration-base` |
| KPIs | Stagger de entrada (ya existe) + `CountUp` en la cifra | 600ms |
| Gráficos Recharts | `isAnimationActive` con easing consistente; líneas dibujadas de izquierda a derecha, barras crecen desde el eje (nativo de Recharts, hoy con defaults inconsistentes) | 800ms una sola vez |
| Tablas | Filas nuevas con `fade-in` sutil al cambiar de página (junto a `keepPreviousData` no hay parpadeo) | `--duration-fast` |
| Hover en fila/card | Cambio de borde + fondo `slate-800/20` (ya existe, se sistematiza) | `--duration-fast` |
| Badge "live" | `animate-pulse-slow` (existe, se conserva como latido del panel) | — |
| Login | Secuencia de entrada única: logo → formulario → footer | `--duration-slow` |

Regla de contención: máximo **una** animación ambiental por vista (el pulso live);
todo lo demás ocurre solo en entrada o interacción. Nada de parallax ni glows
permanentes — el carácter del sistema es instrumental, no decorativo.

## 5. Estándares UX transversales (P4, P6)

1. **Los 4 estados obligatorios** en toda superficie de datos: loading (skeleton),
   error (`ErrorState` con retry), vacío (`EmptyState` con acción), éxito. Se
   auditará página por página en la fase 5.
2. **Accesibilidad (WCAG 2.1 AA):**
   - `focus-visible:ring-2 ring-[--ring-focus]` en todo elemento interactivo.
   - Contraste: subir `text-slate-500` → `text-slate-400` donde sea texto informativo
     (el 500 queda solo para decoración no esencial).
   - `aria-label` en botones de solo icono (campana, colapso de sidebar, paginador).
   - Focus trap + Esc en `Drawer`/modales; `aria-live="polite"` en toasts.
   - `prefers-reduced-motion` cubre el 100% de las animaciones (grep verificable).
3. **Voz de la interfaz:** acciones con verbo exacto ("Descargar Excel", no
   "Exportar"); errores dicen qué pasó y qué hacer; vacíos invitan a actuar;
   sentence case; mismo nombre de la acción en botón → toast.
4. **Responsive:** grids ya colapsan (md/xl); se añade: tablas con scroll horizontal
   contenido en móvil, toolbar de filtros que envuelve a 2 filas, drawer a pantalla
   completa bajo `md`.

## 6. Pasada por página (orden por impacto)

| Página | Cambios principales |
|---|---|
| `DashboardBodega` | Migrar paleta local y `tooltipStyle` a `chartTheme`; tablas G5/G6 → `DataTable` (+paginación); selector de producto de G1 → `Select`; drill-down de artículo → `Drawer` con mini-forecast. Es la página piloto: valida todos los componentes nuevos. |
| `DashboardGerencia` | `chartTheme`, `CountUp` en KPIs, estados vacío/error, transición de ruta. |
| `DashboardVentas` / `DashboardMetas*` | Ídem + `Tabs` donde hoy hay toggles improvisados. |
| `BodegaAlmacenes` | Matriz → `DataTable` con celdas heat (tinte por estado desde tokens), transferencias → `DataTable` + `Drawer` de detalle. |
| `BodegaReportes` | `Button` de descarga con estado loading + `Toast` al completar; vista imprimible sin regresiones. |
| `DashboardAdmin` / `UsersManagement` / `Settings` | Formularios con `Button`/`Select`/`Toast`; confirmaciones destructivas en modal (no `window.confirm`). |
| `Login` | Secuencia de entrada, estados de error del formulario en voz de producto, foco inicial en usuario. |
| `NotFound` / `AccessDenied` | `EmptyState` a pantalla completa con acción de regreso — hoy son las páginas más pobres. |

## 7. Fases de ejecución

| # | Fase | Entregable | Depende de |
|---|---|---|---|
| 1 | Tokens y tema de gráficos | `index.css` ampliado + `chartTheme.ts` + `ChartTooltip` | — |
| 2 | Primitivas nuevas | `Button`, `Select`, `DataTable`, `EmptyState`, `ErrorState`, `Toast`, `Drawer`, `Tabs`, `CountUp`, `Pagination` | 1 |
| 3 | Shell y motion | Transición de ruta en `Layout`, sidebar animado, header/campana, `stagger-children` | 1 |
| 4 | Página piloto | `DashboardBodega` completo con el sistema nuevo | 2, 3 |
| 5 | Resto de páginas | Tabla de §6, en ese orden | 4 |
| 6 | Auditoría final | Checklist §8, limpieza de clases muertas, screenshots comparativos | 5 |

La fase 4 funciona como gate: si el piloto revela fricción en un componente, se
corrige antes de propagarlo (evita refactorizar 13 páginas dos veces).

## 8. Checklist de validación

- [ ] `npx oxlint` + `tsc --noEmit` en verde.
- [ ] `grep -rE '#[0-9a-fA-F]{6}' frontend/src/pages frontend/src/components` → 0 resultados (todo color viene de tokens; excepción documentada: ninguna).
- [ ] Toda animación nueva aparece en el bloque `prefers-reduced-motion`.
- [ ] Navegación completa por teclado: tab por sidebar → filtros → tablas → paginador con foco siempre visible; Esc cierra drawer/modal/dropdown.
- [ ] Contraste AA verificado en textos `slate-400+` sobre `slate-900` (herramienta de contraste sobre los tokens).
- [ ] Los 4 estados (loading/error/vacío/éxito) presentes en cada superficie de datos de las 13 páginas.
- [ ] Responsive: 360px, 768px, 1280px sin scroll horizontal de página (solo interno en tablas).
- [ ] Sin regresión funcional: los 4 dashboards por rol cargan sus datos reales igual que antes (smoke test manual con cada rol).
- [ ] Screenshots antes/después por página (evidencia para la tesis).

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Refactor visual rompe lógica de datos | Los hooks/servicios no se tocan en este plan; solo capa de presentación. La página piloto valida el patrón antes de propagar. |
| Sobre-animación (efecto "AI-generated") | Regla de contención §4: una ambiental por vista, resto solo entrada/interacción; revisión con ojo crítico en fase 6. |
| Alcance simultáneo con el plan de paginación | `Pagination`/`DataTable` se implementan una sola vez aquí (fase 2) y el plan de paginación los consume; coordinar el orden: tokens+primitivas primero. |
| Dependencias nuevas | Ninguna: todo se logra con Tailwind 4 + Recharts + lucide-react ya presentes (sin framer-motion; CSS transitions/animations bastan para este catálogo de motion). |
