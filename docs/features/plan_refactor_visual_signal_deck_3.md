# Plan de refactorización visual — "Signal Deck 3.0"

> **Fecha:** 2026-07-16
> **Alcance:** `frontend/` completo — shell de navegación, primitivas UI, 15 páginas, identidad visual. Solo capa visual: **cero cambios** en rutas, hooks, stores, servicios, contratos API ni lógica de negocio.
> **Estado:** PLAN — pendiente de aprobación antes de implementar.
> **Relación:** sucesor directo de `plan_refactor_ui.md` ("Signal Deck 2.0", 2026-07-12), cuyas fases P1–P6 ya están implementadas y verificadas en código (`chartTheme.ts`, `Button`, `DataTable`, `Toast`, `focus-ring`, skeletons, `prefers-reduced-motion`). Este plan NO repite ese trabajo: cierra sus fugas residuales y cubre lo que aquel plan dejó fuera (arquitectura de navegación, menús desplegables, formularios, Login, responsive de tablas).

---

## 0. Auditoría del estado actual (verificada en código, 2026-07-16)

### Lo que YA existe y se conserva (no rehacer)

| Activo | Evidencia | Decisión |
|---|---|---|
| Design system "Signal Deck" con tokens `@theme` | `index.css`: color, motion (`--ease-out-soft`, `--duration-*`), `focus-ring` accesible, `stagger-children`, `.card`/`.input-field` | **Se conserva y amplifica.** Es la identidad del producto. |
| Tipografía con carácter | Fraunces (display, solo H1) + IBM Plex Sans (cuerpo) + JetBrains Mono (cifras) | Se conserva. Es la decisión anti-genérica más fuerte que ya se tomó. |
| Semántica de procedencia del dato | cian = dato real EDW, ámbar = predicción ML (`--color-provenance-live/ml`, `ChartCard`, `ProvenanceRail`) | **Firma visual del producto.** Se amplifica (ver §2). |
| Tema único de gráficos | `utils/chartTheme.ts` (paleta categórica 8 colores, chrome de Recharts centralizado) | Se conserva. |
| 18 primitivas UI | `components/ui/`: Button, DataTable, Select, Tabs, Drawer, Toast, ConfirmDialog, EmptyState, ErrorState, KpiCard, ChartCard, Pagination, SearchInput, Autocomplete, CountUp, AlertBadge, LoadingSpinner, ChartTooltip | Base sólida; se extienden, no se reescriben. |

### Deuda visual real encontrada (lo que hace que se sienta "genérico")

| # | Problema | Evidencia |
|---|---|---|
| D-1 | **Los tokens existen pero los componentes los evaden.** ~145 usos de paleta Tailwind cruda en `.tsx` (`text-cyan-400` ×43, `text-red-400` ×30, `text-amber-400` ×19, `text-emerald-400` ×15, más `teal`, `blue`, `rose`, `sky`, `purple` sueltos). Los tokens semánticos (`--color-accent`, `--color-danger`, `--color-success`, `--color-warning`) casi no se consumen desde las clases. | `grep -roE "text-(blue\|teal\|…)-[0-9]+"` sobre `frontend/src` |
| D-2 | **Colores fuera de sistema en el shell.** El Sidebar usa `blue-500` (logo), `blue-400/blue-500-10` (ítem activo) y `teal-400` (sub-ítems) — tres acentos distintos que compiten con el cian oficial del sistema. | `Sidebar.tsx:55,71,96` |
| D-3 | **`Button` incompleto → parches por página.** Solo 3 variantes (`primary/ghost/danger`); `DashboardGerencia.tsx:102` lo fuerza con `!bg-emerald-600 !border-emerald-600` para lograr un botón "success". Faltan `secondary`, `success`, `outline`, tamaño `lg`, `iconRight`, solo-icono. | `Button.tsx`, `DashboardGerencia.tsx:99-106` |
| D-4 | **Sin menús desplegables en ningún nivel** (queja explícita del usuario). El Sidebar pinta los sub-ítems siempre expandidos (sin acordeón, sin estado abierto/cerrado, sin persistencia, sin modo colapsado-solo-iconos). El Header no tiene menú de usuario (logout es un icono suelto); no existe primitiva `Dropdown`/`Menu` en `components/ui/`. | `Sidebar.tsx:86-106`, `Header.tsx:50-57` |
| D-5 | **Header pobre.** Sin breadcrumb (el usuario no sabe dónde está en rutas anidadas tipo `/ventas/cross-selling`), sin menú de usuario, avatar genérico sin iniciales, chip de sucursal como único contenido. | `Header.tsx` |
| D-6 | **Login genérico.** Card centrada sobre fondo plano — exactamente la plantilla que cualquier generador produce. Inputs escritos a mano (no hay primitiva `Input`/`FormField`); el ícono `Building2` + "BI Platform" no comunica identidad. | `Login.tsx:57-135` |
| D-7 | **No existe primitiva de formulario.** Login, UsersManagement, Settings y los paneles de configuración duplican el patrón label + icono + input + error con clases crudas; `.input-field` (CSS) cubre solo el caso básico sin label/error/helper. | `Login.tsx:83-118`, `UsersManagement.tsx`, `Settings.tsx` |
| D-8 | **Tablas sin orden ni responsive.** `DataTable` no soporta ordenamiento por columna; en móvil solo hace scroll horizontal (las filas nunca colapsan a cards). | `DataTable.tsx` |
| D-9 | **Dos sistemas de stagger conviviendo.** `animDelay` numérico pasado a mano (`KpiCard`, `Login`) vs. `stagger-children` (posterior, mejor). Inconsistencia interna del propio sistema. | `KpiCard.tsx:12,29`, `Login.tsx:60-82` vs `index.css:152-163` |
| D-10 | **Barras de filtros ad-hoc.** Cada dashboard improvisa su contenedor de filtros con clases distintas (`bg-slate-800/50 rounded-lg border-slate-700/50` en Gerencia vs `BodegaFilterBar` como componente en Bodega). | `DashboardGerencia.tsx:117`, `components/bodega/BodegaFilterBar.tsx` |
| D-11 | **Sin primitiva `Tooltip` ni `Badge` unificado.** `AlertBadge` existe pero cada página inventa chips propios (`Header.tsx:29` chip de sucursal a mano). | `components/ui/` |
| D-12 | **Tema oscuro único, sin capa de theming.** Los tokens están en `@theme` pero mezclados con clases `slate-*` literales en `@layer base` y en todos los componentes — imposible introducir un tema claro sin tocar cada archivo. (No se pide modo claro hoy; se pide no bloquearlo.) | `index.css:60-79`, global |

**Diagnóstico rector:** igual que en 2.0, el problema no es ausencia de sistema sino **cobertura incompleta y disciplina rota**. La sensación de "genérico" viene de: (a) el shell de navegación — lo primero que se ve — usa colores fuera de sistema y carece de los patrones que un SaaS maduro tiene (desplegables, menú de usuario, breadcrumb, colapsado); (b) el Login — la primera pantalla — es una plantilla; (c) las páginas evaden los tokens, diluyendo la identidad en una sopa de cian/teal/azul/esmeralda.

---

## 1. Reglas del refactor (invariantes)

1. **No se toca:** `router/`, `hooks/`, `store/` (salvo agregar estado UI puro, p. ej. grupos abiertos del sidebar), `services/`, `types/` (salvo tipos de props visuales), validaciones, flujo de auth.
2. **Stack:** React 19 + TypeScript + Tailwind 4 + lucide-react + Recharts. Se agrega **una sola dependencia nueva: Framer Motion** (decisión de la Fase 0, §2.4), con alcance acotado a presencia/salida/layout — las micro-transiciones siguen en CSS. **No se agregan** Radix/shadcn (las primitivas necesarias son pequeñas y propias) ni React Hook Form/Zod (tocarían lógica de formularios = prohibido por invariante 1).
3. **Regla de tokens (verificable con grep en la validación):** ningún `.tsx` nuevo o tocado usa paleta Tailwind cruda de acento (`cyan-*`, `teal-*`, `blue-*`, `emerald-*`, `red-*`, `amber-*`, etc.) — solo clases derivadas de tokens (`text-accent`, `bg-danger-dim`, …) o `slate-*` para neutros (los neutros se migran a tokens `surface/border/text` en F1 para no bloquear theming, D-12).
4. Cada fase termina con: `npm run build` (tsc + vite) y `npm run lint` (oxlint) en verde, y verificación visual manual de las páginas afectadas por rol.
5. Commits por fase, nunca un mega-commit.

---

## 2. Fase 0 — Dirección creativa (visión del producto)

> Esta sección es la fuente de verdad del *lenguaje visual*. Toda decisión de las fases F1–F8 se deriva de aquí; ante ambigüedad, gana esta sección.

### 2.1 Qué es este producto y qué debe transmitir

Esta aplicación no es un CRUD administrativo: es una **plataforma de Business Intelligence** para análisis, monitoreo, indicadores y toma de decisiones, usada durante horas al día por operadores (gerencia, ventas, bodega, admin). La interfaz debe transmitir de inmediato: **precisión, inteligencia, velocidad, tecnología, elegancia, profesionalismo, confianza**.

Referencias de nivel de calidad (inspiración, nunca copia): **Linear** (minimalismo), **Vercel** (modo oscuro elegante), **Grafana** (visualización de datos), **Supabase** (jerarquía visual), **Stripe Dashboard** (UX), **Arc Browser / Raycast** (profundidad y animación), **Notion Dark**, **Apple Pro Apps**. El resultado debe sentirse como una plataforma BI de nueva generación con identidad propia, no como una plantilla administrativa — y explícitamente **no** como un dashboard de Dribbble (degradados saturados, pasteles, decoración): eso fatiga la vista en jornadas de 8 horas. Sofisticación con claridad; el objetivo no es "que se vea bonita" sino que la interfaz guíe la atención hacia los indicadores críticos y acelere la decisión (*data storytelling*).

### 2.2 Paleta — modo oscuro por capas de profundidad

Modo oscuro como tema principal. **Sin negros absolutos**: múltiples capas de superficie que generan profundidad por contraste, no por sombras agresivas. Esta paleta reemplaza los valores actuales de `@theme` en F1:

| Token | Valor | Uso |
|---|---|---|
| `bg-base` | `#0B0F19` | Fondo principal |
| `bg-sidebar` | `#101624` | Sidebar |
| `bg-surface` | `#121826` | Superficie base de paneles |
| `bg-card` | `#171F31` | Cards |
| `bg-elevated` | `#1A2235` | Popovers, dropdowns, modales |
| `bg-hover` | `#202A40` | Estado hover de superficies |
| `border` | `rgba(255,255,255,.06)` | Bordes hairline (nunca gruesos) |
| `text-primary` | `#F8FAFC` | Texto principal |
| `text-muted` | `#94A3B8` | Texto secundario |
| `text-disabled` | `#64748B` | Deshabilitado |
| `primary` | `#6D5DF6` | Acento de interacción/marca (botones, activo, foco) |
| `accent` | `#8B5CF6` | Acento complementario (gradientes discretos con primary) |
| `info` | `#38BDF8` | Informativo |
| `success` | `#22C55E` | Éxito |
| `warning` | `#F59E0B` | Advertencia |
| `danger` | `#EF4444` | Peligro |

Regla de uso: **el color es un punto de atención, nunca relleno**. El fondo permanece oscuro; los acentos destacan solo información importante o interacción.

**Reconciliación con la identidad existente (decisión de diseño):** la firma de Signal Deck — *procedencia del dato como color* — **se conserva pero se re-mapea**: el violeta `primary` pasa a ser el color de interacción y marca (rol que hoy ocupa el cian de forma ambigua), y el **cian `info` queda reservado en exclusiva para "dato real del EDW"** vs. **ámbar `warning` para "predicción ML"** (`--color-provenance-live/ml`, `ChartCard`, `ProvenanceRail`). Esto resuelve la ambigüedad actual donde el cian significa a la vez "botón" y "dato vivo", y le da al producto dos capas legibles: violeta = tú interactúas, cian/ámbar = el dato habla.

### 2.3 Profundidad e iluminación

- Capas de superficie (tabla 2.2) como mecanismo primario de profundidad; sombras suaves y difusas como refuerzo, nunca protagonistas.
- **Glassmorphism muy ligero** solo en superficies flotantes (dropdowns, modales, toasts, header sticky): `backdrop-blur` sutil + fondo semitransparente de `bg-elevated`. Nunca en paneles de datos (legibilidad primero).
- Iluminación sutil para dirigir la atención: glows pequeños en `primary` (elemento activo del sidebar, foco), highlights de 1px en el borde superior de cards elevadas, gradientes muy discretos (`primary→accent`) reservados a la marca y a máximo un elemento por vista. Nada saturado.

### 2.4 Movimiento — la interfaz nunca se siente estática, nunca estorba

- Duraciones permitidas: **120 / 180 / 250 / 300 ms**. Máximo absoluto 400 ms (solo entradas orquestadas de página). Se re-mapean los tokens `--duration-*` a esta escala.
- Todo elemento interactivo responde: botones (hover/pressed), inputs (foco), cards (hover lift de 1-2px + borde), tabs (indicador deslizante), dropdowns/modales/drawers (entrada con fade+scale/slide), toasts, tooltips, contadores de KPI (`CountUp` ya existe), gráficas (entrada animada de Recharts), skeletons (shimmer ya existe), sidebar (colapso animado), breadcrumb y filtros (transición al cambiar).
- **Framer Motion se incorpora** (decisión del brief, revierte el descope de 2.0) con alcance acotado: animaciones de presencia/salida y layout (dropdowns, modales, drawer, acordeón del sidebar, reordenamientos) donde CSS no llega limpio. Las micro-transiciones simples (hover, foco, color) siguen en CSS/tokens — no se envuelve toda la app en motion components.
- `prefers-reduced-motion` sigue siendo ley en todo lo nuevo.

### 2.5 Tipografía y estructura (se conserva de 2.0)

- Fraunces (display, solo H1) + IBM Plex Sans (cuerpo) + JetBrains Mono (cifras): es la decisión anti-genérica más fuerte ya tomada y sobrevive al cambio de paleta.
- Iconografía: **solo Lucide**, un solo grosor de trazo, tamaños de la escala (16/18/20).
- Aire generoso entre paneles, datos densos dentro de ellos: es un instrumento de trabajo, no un sitio de marketing.
- Estructura que informa: grupos del Sidebar por dominio real (`permissions.ts`), breadcrumb de la jerarquía de rutas real, cero decoración estructural.
- El riesgo estético se gasta en el **Login** (F6): split layout con panel "instrumento en vivo" — visualización ambiental abstracta con los tokens del sistema (pulso tipo osciloscopio en cian sobre grid tenue, gradiente discreto violeta en la marca), CSS puro, congelada bajo `prefers-reduced-motion`.

### 2.6 Experiencia final (criterio de percepción)

Al abrir la aplicación el usuario debe pensar: *"transmite confianza"*, *"los datos son fáciles de leer"*, *"todo tiene jerarquía clara"*, *"se siente rápida, moderna, exclusiva"*, *"da gusto trabajar aquí durante horas"*. Este criterio subjetivo se valida en la sesión de revisión visual por rol de cada fase.

---

## 3. Fases de implementación

Orden por impacto visible / riesgo: primero disciplina de tokens (base de todo), luego el shell (lo que se ve en todas las páginas), luego primitivas nuevas, luego páginas.

### F1 — Nueva paleta por capas + disciplina de tokens (base de todo)

1. Reescribir los tokens de color de `@theme` en `index.css` con la paleta de la Fase 0 (§2.2): capas de profundidad `base/sidebar/surface/card/elevated/hover`, borde hairline `rgba(255,255,255,.06)`, violeta `primary`/`accent`, semánticos `info/success/warning/danger`, y re-mapeo de procedencia (`provenance-live` = `info` cian, `provenance-ml` = `warning` ámbar). Re-mapear `--duration-*` a la escala 120/180/250/300 ms (§2.4). Actualizar `chartTheme.ts` para resolver desde los nuevos valores (Recharts exige strings planos).
2. Migrar los ~145 usos de paleta cruda (D-1) a clases de token, archivo por archivo. Mapeo: `cyan-*` de interacción → `primary`; `cyan-*` de dato/procedencia → `info`; `red-400→danger`, `amber-400→warning`, `emerald/green-400→success`, `teal-*/blue-*→primary` (unificación deliberada, D-2).
3. Migrar los `slate-*` estructurales de componentes compartidos (`.card`, DataTable, Drawer, Toast…) a las capas `surface/card/elevated/hover` y `text-primary/muted/disabled` (D-12). Los `slate-*` de páginas se migran al tocar cada página en F6.
4. Unificar stagger: eliminar la prop `animDelay` de `KpiCard` y usos, reemplazar por `stagger-children` en los contenedores (D-9).
5. Instalar Framer Motion y crear `utils/motion.ts` con variantes compartidas (fade, slide, scale, presencia) usando las duraciones de la escala — una sola fuente de verdad de motion para F2+.
- **Verificación:** grep de la regla 3 en archivos tocados = 0 resultados; build + lint; revisión visual: es el cambio de piel global (violeta como acento, capas de profundidad) — se revisan las 15 páginas en modo lectura rápida buscando texto ilegible o contraste roto.

### F2 — Primitivas nuevas: `Dropdown`, `Tooltip`, `Badge`, `Collapse` (D-4, D-11)

Componentes pequeños, propios, con el motion y focus-ring del sistema:

1. `ui/Dropdown.tsx` — menú desplegable accesible (trigger + panel posicionado, cierre por click-fuera/Escape, navegación por flechas, `role="menu"`). Base del menú de usuario (F3) y de las acciones agrupadas en tablas (F5).
2. `ui/Tooltip.tsx` — CSS-first (hover/focus), para el sidebar colapsado y acciones solo-icono.
3. `ui/Badge.tsx` — chip unificado (variantes semánticas + `dot`), absorbe los chips a mano (`Header`, páginas); `AlertBadge` queda como alias deprecado hasta F6.
4. `ui/Collapse.tsx` — contenedor acordeón con animación de altura (grid-rows CSS trick, sin JS de medición), para los grupos del Sidebar.
- **Verificación:** build + lint; smoke test manual de teclado (Tab/Escape/flechas) en cada primitiva.

### F3 — Shell: Sidebar desplegable + Header con menú de usuario y breadcrumb (D-2, D-4, D-5)

**Sidebar** (la queja central del usuario):

1. Grupos por dominio con **acordeón desplegable** (`Collapse`): ítems con sub-rutas (Gerencia, Bodega, Ventas) muestran chevron y se expanden/colapsan; el grupo de la ruta activa se abre solo.
2. **Modo colapsado a solo-iconos** en desktop (botón en el borde del sidebar), con `Tooltip` mostrando el label; estado persistido en `uiStore` + `localStorage` (estado UI puro, permitido por invariante 1).
3. Móvil: se conserva el drawer actual (ya funciona), se le agrega overlay con `animate-overlay-enter` si falta.
4. Colores a sistema: fondo `bg-sidebar` (capa propia, §2.2); ítem activo = `primary` con la barra lateral existente + **glow muy ligero** en violeta (§2.3); hover elegante (`bg-hover`, 180 ms); sub-ítems mismo acento, jerarquía por tipografía/indentación, no por color distinto; separadores hairline entre grupos; `Badge` para contadores (p. ej. notificaciones no leídas si el dato ya está en el store — sin llamadas nuevas).
5. Marca: reemplazar `Building2` azul por una marca tipográfica propia (nombre real de la plataforma de la tesis) con punto de pulso en gradiente discreto `primary→accent` — único gradiente del shell.
5b. **Bloque de perfil al pie del sidebar** (patrón Linear/Supabase): avatar con iniciales + nombre + rol, indicador de sesión activa, que abre el mismo `Dropdown` de usuario de F3.6 — el perfil vive en ambos puntos (header y sidebar) porque el sidebar colapsado lo oculta. El "cambio de workspace" del brief se adapta a lo que este dominio realmente tiene: el chip de **sucursal** del usuario (dato ya presente en `authStore`); no se inventa un selector sin backend.

**Header:**

6. **Menú de usuario desplegable** (`Dropdown`): avatar con iniciales reales + nombre/rol; ítems: Configuración (`/settings`, se saca del Sidebar donde hoy ocupa el footer) y Cerrar sesión (con confirmación visual, no icono suelto).
7. **Breadcrumb** derivado de `permissions.ts` (los labels ya existen ahí — cero fuente de verdad nueva).
8. Chip de sucursal migra a `Badge`.
- **Verificación:** build + lint; recorrido manual con los 4 roles (el mapa de navegación por rol NO cambia, solo su presentación); teclado completo en sidebar y menú.

### F4 — Formularios: `Input` / `FormField` (D-7)

1. `ui/Input.tsx` — input con variantes de estado (default/error/success/disabled), icono izquierdo/derecho, mismo lenguaje visual que `Select`/`.input-field`.
2. `ui/FormField.tsx` — composición label + control + helper/error text (`aria-describedby`, `aria-invalid`).
3. Migrar Login, UsersManagement y Settings a estas primitivas **sin tocar su lógica de submit/validación** (los `useState` y handlers quedan idénticos; solo cambia el JSX de presentación).
- **Verificación:** build + lint; login real contra backend en dev; alta/edición de usuario en dev.

### F5 — Tablas "Notion + Linear" (D-8)

1. `DataTable`: prop opcional `sortable` por columna (orden client-side sobre `data` ya cargada — no toca queries ni paginación server-side; las columnas con paginación server quedan sin sort o con sort deshabilitado explícito).
2. Patrón responsive: bajo `md`, las filas se renderizan como cards apiladas (label de columna + valor) usando las mismas `columns` — opt-in por prop `responsive` para migrar tabla por tabla sin big-bang.
3. Acciones por fila agrupadas en `Dropdown` (⋯) donde hoy hay botones sueltos (UsersManagement).
4. Pulido de percepción (§2.1): hover de fila elegante (`bg-hover`, 120 ms), fila seleccionada/expandida con borde `primary` sutil, sticky header (ya existe) + **sticky de primera columna** opt-in para tablas anchas (matrices de Bodega), toolbar de tabla estándar (búsqueda en vivo client-side con `SearchInput` existente + chips de filtros activos con `Badge`), skeleton animado (ya existe).
5. **Selección múltiple queda fuera**: ninguna vista actual tiene una acción por lotes en la API; agregar checkboxes sin acción sería decoración (contra §2.2 "el color es un punto de atención"). Se reevalúa si aparece un caso de negocio.
- **Verificación:** build + lint; verificación visual en 375px/768px/1280px de UsersManagement, stock-reorden (paginada server-side: sort deshabilitado) e inventario-matriz (sticky first column).

### F6 — Login "instrumento en vivo" + barrido final de páginas (D-6, D-10, resto D-1)

1. Rediseño del Login según §2: split layout (panel instrumento + formulario con `FormField`), branding tipográfico propio, animación CSS ambiental con `prefers-reduced-motion`. La lógica (`handleLogin`, stores, servicios) no se toca.
2. `ui/FilterBar.tsx` — contenedor estándar de filtros (absorbe el ad-hoc de Gerencia; `BodegaFilterBar` lo adopta como wrapper) (D-10).
3. Barrido página por página (15 páginas): tokens residuales, `stagger-children`, `Badge`, espaciado en escala de 8px, jerarquía de encabezados (un solo H1 Fraunces por página).
4. Limpieza: eliminar `AlertBadge` (alias), prop `animDelay`, clases muertas, `COLORS` deprecado de `chartTheme` si ya no tiene usos.
- **Verificación:** build + lint; grep global de la regla de tokens = 0 en todo `frontend/src`; recorrido completo de los 4 roles en dev contra backend real; revisión de contraste AA en textos `text-muted` sobre `surface` (ajustar el token una sola vez si falla, no por página).

### F7 — KPIs y gráficas protagonistas (data storytelling)

Los KPIs y las gráficas son el corazón de una plataforma BI; aquí se invierte el detalle visual que el brief pide, siempre sobre datos que **ya llegan** en las respuestas actuales (cero endpoints nuevos).

1. `KpiCard` 2.0: ícono + título + valor grande en mono con `CountUp` (ya existe) + comparación/variación con flecha y color semántico (ya existe) + **sparkline** opcional (mini `AreaChart` Recharts de ~40px con gradiente `primary` al 10%, solo cuando la página ya tiene la serie — p. ej. la serie de predicción en Gerencia) + tooltip con `Tooltip` de F2 + hover lift + estado (`success/warning/danger`) como highlight de borde superior de 1px.
2. Gráficas Recharts, vía `chartTheme` y un wrapper de props comunes: entrada animada (`isAnimationActive` con duración de la escala), **gradientes de área** discretos (fill `primary`/`info` al 8-12%, del color de la serie a transparente — el único gradiente permitido en paneles de datos), crosshair (`Tooltip cursor` estilizado), tooltips modernos (`ChartTooltip` ya existe: se le da vidrio ligero §2.3), leyendas limpias (payload custom, punto + label en `text-muted`), dots activos con borde `bg-card` para que "floten".
3. `ChartCard` 2.0: título + badge de procedencia (ya existe) + fila de acciones estándar — **fullscreen** (modal `bg-elevated` reutilizando `Drawer`/modal de F2, re-render del mismo chart a tamaño completo) y **exportar PNG** client-side (serialización del SVG de Recharts a canvas; sin backend).
4. **Zoom/selección de rango**: `Brush` de Recharts opt-in solo en las series temporales largas (predicción de ventas en Gerencia, forecast de salidas en Bodega). No se agrega a gráficas categóricas.
- **Verificación:** build + lint; revisión visual de los 4 dashboards; performance: las animaciones de Recharts se desactivan en tablas de >50 puntos si se percibe jank (medir con Performance panel, no adivinar).

### F8 — Dashboard como centro de inteligencia (composición final)

Con todas las piezas anteriores, se recompone la jerarquía de cada dashboard para que guíe la atención (§2.6): banda de KPIs arriba (protagonistas, F7), gráficas principales al centro, tablas de trabajo abajo; alertas/`Badge` de estado del sistema visibles sin scroll.

1. Gerencia: KPIs con sparkline + cumplimiento de meta como indicador de estado; filtros globales en `FilterBar` (F6) con selector de rango de fechas existente; exportaciones (Excel/PDF ya existen) como acciones rápidas en la cabecera.
2. Ventas/Bodega/Admin: misma recomposición con sus datos actuales; "actividad reciente" y "estado del sistema" se cubren con lo que ya existe (`NotificationBell` + historial de notificaciones, `GET /system/provenance` en `ProvenanceRail`) — presentados con más jerarquía, no con endpoints nuevos.
3. **Widgets reorganizables (drag & drop) quedan explícitamente fuera**: exigen persistencia de layout por usuario (backend nuevo) y una librería DnD; costo/beneficio negativo para una tesis. El orden de widgets se decide bien una vez en diseño, que es lo que un buen default hace.
- **Verificación:** build + lint; sesión de percepción §2.6 con los 4 roles; Network sin peticiones nuevas.

---

## 4. Qué NO entra en este plan (descope explícito)

- **Modo claro:** F1 deja el theming desbloqueado (todo por tokens), pero no se implementa un segundo tema. El modo oscuro por capas ES la identidad (§2.2); un tema claro sería otra decisión de producto.
- **Command palette / buscador global del Header:** no hay endpoint de búsqueda global en la API; inventarlo viola el invariante de no tocar backend. Se reevalúa si algún día existe. (La búsqueda en vivo *por tabla* sí entra, F5.4 — es client-side.)
- **Librerías nuevas salvo Framer Motion** (Radix, shadcn, RHF, Zod): ver invariante 2.
- **Selección múltiple en tablas** (F5.5) y **widgets reorganizables** (F8.3): sin acción de negocio ni backend que los respalde; decoración.
- **Cambio de workspace:** este dominio no tiene workspaces; se adapta como chip de sucursal (F3.5b).
- **Ripple material:** el lenguaje §2.3 usa profundidad y glow sutil, no ripples de Material Design — mezclar lenguajes es lo que hace ver genérica una UI.
- **Reescritura de gráficos:** `chartTheme` ya centraliza Recharts; F7 lo extiende, no lo reemplaza.
- **Transiciones entre rutas más allá de `animate-route-enter`** (ya existe): la View Transitions API se descarta por soporte y riesgo/beneficio.

## 5. Estimación y orden de commits

| Fase | Alcance | Riesgo de regresión |
|---|---|---|
| F1 | Paleta nueva + ~30 archivos de migración de tokens + motion.ts | Bajo-medio (visual-only pero cambia la piel completa; diff revisable) |
| F2 | 4 archivos nuevos | Nulo (nada los consume aún) |
| F3 | Sidebar, Header, uiStore, permissions (solo lectura) | Medio — es el shell; mitigado con recorrido por rol |
| F4 | 2 primitivas + 3 páginas | Medio — formularios de auth/usuarios; mitigado probando login y CRUD real |
| F5 | DataTable + 2-3 páginas | Bajo — features opt-in |
| F6 | Login + barrido 15 páginas | Bajo por página, volumen alto |
| F7 | KpiCard/ChartCard 2.0 + wrappers Recharts | Bajo-medio — visual, pero vigilar performance de animaciones |
| F8 | Recomposición de 4 dashboards | Bajo — reordena, no cambia datos |

Cada fase es independiente y entregable por separado; si se corta el trabajo tras F3, el usuario ya tiene resuelto lo que motivó el plan original (navegación desplegable + shell no-genérico); F7–F8 son las que materializan la ambición "plataforma BI de nueva generación" de la Fase 0.

## 6. Criterios de aceptación globales

1. `npm run build` y `npm run lint` en verde.
2. `grep -roE "text-(cyan|teal|blue|emerald|green|red|amber|rose|sky|purple|violet)-[0-9]+" frontend/src --include="*.tsx"` → 0 resultados (equivalente para `bg-`/`border-`).
3. Sidebar: grupos desplegables con persistencia, modo colapsado con tooltips, drawer móvil, teclado completo.
4. Header: menú de usuario desplegable, breadcrumb, sin acciones sueltas.
5. Los 4 roles ven exactamente las mismas rutas y datos que antes (la matriz de `permissions.ts` no cambia).
6. Focus visible en todo elemento interactivo; `prefers-reduced-motion` respetado en toda animación nueva.
7. Ninguna petición HTTP nueva ni cambiada (verificable en la pestaña Network durante el recorrido por rol).
8. Paleta §2.2 aplicada: capas de profundidad `base/sidebar/surface/card/elevated/hover`, violeta como único acento de interacción, cian/ámbar reservados a procedencia del dato.
9. Toda animación dentro de la escala 120–300 ms (400 ms máximo en entradas de página); ninguna interfaz estática — hover/foco/entrada responden en todos los componentes interactivos.
10. Sesión de percepción (§2.6) superada con los 4 roles: jerarquía clara, indicadores críticos visibles sin scroll, sensación de velocidad.
