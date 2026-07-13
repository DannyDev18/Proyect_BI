# 📦 MÓDULO BODEGA - DASHBOARD PARA GESTIÓN DE INVENTARIO Y ABASTECIMIENTO

---

## OBJETIVO DEL MÓDULO

El módulo Bodega está diseñado para que el encargado de bodega pueda tomar decisiones estratégicas de abastecimiento basadas en datos históricos y predicciones de machine learning. El sistema debe permitir identificar qué productos tienen mayor rotación, cuándo y cuánto comprar, y optimizar el inventario mediante transferencias inteligentes entre bodegas antes de realizar nuevos pedidos a proveedores.

---

## 1. DASHBOARD PRINCIPAL

### 1.1 Filtros Globales

El dashboard debe contar con los siguientes filtros que afectan a todos los gráficos y datos mostrados:

- **Selector de Almacén**: Lista de todas las bodegas (ALMACEN ATAHUALPA, ALMACEN EL REY, ALMACEN ZAMBA, etc.) con opción "Todas las bodegas" para vista consolidada.
- **Selector de Mes**: Selector de mes y año para filtrar los datos históricos que se visualizan.
- **Selector de Categoría**: Filtrar por categoría de producto (BAT, REP, Z-999, HER, SON, LED01, KARCH, etc.) con opción "Todas las categorías".
- **Selector de Rango de Fechas**: Permite seleccionar un período personalizado con fecha de inicio y fecha de fin.
- **Selector de Proveedor**: Filtrar por proveedor para identificar qué artículos se compran a cada uno.
- **Selector de Tipo de Movimiento (Kardex)**: Filtra artículos según el tipo de movimiento de Kardex que han tenido (Ventas/facturas, Transferencias entre bodegas, Egresos, Compras, Devoluciones, Ingresos, Ajustes de bodega, Ajustes/decrementos — catálogo `kardex.tiporg`, docs/auditoria/02_reglas_negocio_validadas.md §3), con opción "Todos los movimientos".

**Comportamiento**: Todos los gráficos y KPIs se actualizan automáticamente al cambiar cualquier filtro. Los filtros deben persistir en la sesión del usuario.

---

### 1.2 KPIs Principales (Tarjetas Superiores)

El dashboard debe mostrar seis indicadores clave en la parte superior:

**1. Total de Artículos en Inventario**
- Número total de SKU únicos disponibles en la bodega seleccionada
- Tendencia vs mes anterior (ejemplo: ▲ +3.2%)
- Desglose por estado: "Activos" y "Con stock cero"

**2. Rotación de Inventario**
- Veces que se ha vendido y repuesto el inventario en el período
- Fórmula: Costo de ventas / Inventario promedio
- Indicador de color: Verde (>4 veces/año = buena rotación), Amarillo (2-4 veces/año = regular), Rojo (<2 veces/año = mala rotación)

**3. Días de Inventario Disponible**
- Promedio de días que durará el inventario actual
- Fórmula: (Inventario actual / Ventas promedio diarias) × 30
- Mostrar alerta si es menor a 15 días (riesgo de desabastecimiento)

**4. Productos con Stock Bajo**
- Cantidad de productos cuyo stock está por debajo del punto de reorden
- Color: Rojo si es >10% del total de productos, Amarillo si es 5-10%, Verde si es <5%
- Al hacer click, filtrar la tabla de productos para ver esos artículos

**5. Valor Total del Inventario**
- Suma del costo total de todo el inventario en la bodega
- Tendencia vs mes anterior
- Desglose por categoría (top 5 categorías en valor)

**6. Tasa de Agotados (Stockouts)**
- Porcentaje de días en que productos estuvieron sin stock en el mes
- Meta: <3% de los productos deben tener stockout
- Alerta si supera el 5%

---

### 1.3 Gráficos para Toma de Decisiones

#### Gráfico 1: Histórico y Predicción de Salidas por Producto

**Propósito**: Visualizar qué productos han tenido mayor salida en el mes y proyectar las salidas futuras para planificar compras.

**Descripción**:
- **Tipo**: Gráfico de líneas con área sombreada (similar al de ventas)
- **Eje X**: Días del mes (histórico + predicción)
- **Eje Y**: Cantidad de unidades salidas

**Líneas a Mostrar**:
- **Salidas Reales (Histórico)**: Línea azul sólida (#2563EB) que muestra las salidas reales del mes
- **Predicción ML**: Línea naranja punteada (#F59E0B) que proyecta las salidas para los próximos días
- **Banda de Confianza (80%)**: Área sombreada naranja con transparencia
- **Punto de Reorden**: Línea horizontal roja discontinua que muestra el nivel de stock mínimo antes de reabastecer
- **Stock Actual**: Línea horizontal verde que muestra el inventario actual

**Interactividad**:
- Dropdown para seleccionar producto específico o "Top 10 productos"
- Hover muestra valores exactos y proyecciones
- Click en un producto abre su detalle individual

**Notificación**: Si la predicción indica que un producto llegará al punto de reorden en menos de 7 días, generar notificación en el icono de notificaciones.

---

#### Gráfico 2: Matriz de Rotación y Rentabilidad por Producto

**Propósito**: Identificar qué productos tienen alta rotación y alto margen (prioridad de abastecimiento) vs productos de baja rotación (candidatos a transferencia o descuento).

**Descripción**:
- **Tipo**: Scatter plot con burbujas (matriz)
- **Eje X**: Velocidad de rotación (veces que se vende al mes)
- **Eje Y**: Margen de contribución por unidad

**Cuadrantes**:
- **Superior Derecho (Alta Rotación + Alto Margen)**: Productos prioridad #1 para abastecimiento. Mantener stock alto.
- **Inferior Derecho (Alta Rotación + Bajo Margen)**: Productos que se venden mucho pero con bajo margen. Mantener stock suficiente pero buscar mejorar precios.
- **Superior Izquierdo (Baja Rotación + Alto Margen)**: Productos que se venden poco pero dejan buen margen. Mantener stock bajo y promocionar.
- **Inferior Izquierdo (Baja Rotación + Bajo Margen)**: Productos candidatos a transferencia, descuento o descontinuación.

**Tamaño de burbuja**: Valor total del inventario de ese producto

**Información en Tooltip**:
- Nombre del producto
- Rotación mensual
- Margen por unidad
- Stock actual
- Días de inventario disponible

---

#### Gráfico 3: Top 20 Productos con Mayor Salida (Barras Horizontales)

**Propósito**: Identificar los productos más vendidos del mes para priorizar su abastecimiento.

**Descripción**:
- **Tipo**: Barras horizontales
- **Eje Y**: Nombre de los 20 productos con mayor salida
- **Eje X**: Cantidad de unidades vendidas/salidas

**Color por Categoría**: Cada barra coloreada según la categoría del producto (BAT, REP, Z-999, etc.)

**Información Adicional**:
- Mostrar stock actual al final de cada barra (ejemplo: "Stock: 45 unidades")
- Mostrar días de inventario disponible (ejemplo: "15 días")
- Indicador de tendencia vs mes anterior (↑ si creció, ↓ si decreció)

**Interactividad**:
- Click en cualquier producto abre su detalle completo
- Botón "Ver todos los productos" para tabla completa

**Decisión que permite**: Identificar qué productos deben estar siempre en stock y cuáles deben priorizarse en el próximo pedido.

---

#### Gráfico 4: Distribución de Salidas por Categoría (Pastel o Barras Apiladas)

**Propósito**: Entender qué categorías de productos son las que más se mueven para orientar las decisiones de abastecimiento.

**Descripción**:
- **Tipo**: Gráfico de pastel o barras 100% apiladas
- **Cada categoría**: Porcentaje de participación en salidas totales
- **Color por categoría**: Bat (azul), Rep (verde), Z-999 (naranja), etc.

**Información Adicional**:
- Mostrar valor absoluto de unidades por categoría
- Comparativa vs mes anterior (ejemplo: "BAT: +12% vs mes anterior")
- Stock disponible por categoría

**Decisión que permite**: Si una categoría representa el 40% de las salidas, debe tener mayor prioridad de abastecimiento que otra que solo representa el 5%.

---

#### Gráfico 5: Estado de Stock vs Punto de Reorden (Barras o Tabla Visual)

**Propósito**: Mostrar qué productos están cerca de agotarse y requieren acción inmediata.

**Descripción**:
- **Tipo**: Barras horizontales o tabla con barras de progreso
- **Cada producto**: Barra que muestra stock actual vs punto de reorden
- **Color**: 
  - Rojo si stock < punto de reorden (crítico)
  - Amarillo si stock está entre punto de reorden y punto de reorden × 1.5 (cerca)
  - Verde si stock > punto de reorden × 1.5 (seguro)

**Columnas a Mostrar**:
- Código y nombre del producto
- Stock actual
- Punto de reorden configurado
- Días estimados hasta agotarse (basado en salidas promedio)
- Estado (Crítico, Cerca, Seguro)

**Acciones**:
- Botón "Solicitar Compra" para productos en crítico
- Botón "Sugerir Transferencia" para productos con exceso en otra bodega

**Notificación**: Productos en estado "Crítico" generan notificación automática en el icono de notificaciones.

---

#### Gráfico 6: Predicción de Necesidad de Compra por Producto

**Propósito**: Proyectar qué productos necesitarán ser comprados en las próximas semanas para evitar desabastecimiento.

**Descripción**:
- **Tipo**: Tabla con colores o gráfico de barras horizontales
- **Mostrar para cada producto**: Fecha estimada en que llegará al punto de reorden
- **Ordenar**: Por fecha más cercana (los que se agotarán primero)

**Columnas**:
- Producto (nombre y código)
- Stock actual
- Salidas promedio diarias (últimos 30 días)
- Días hasta punto de reorden
- Fecha estimada de llegada a punto de reorden
- Cantidad sugerida a comprar (basada en proyección de 30 días)

**Interactividad**:
- Click en producto abre detalle de proyección
- Botón "Generar Orden de Compra" para productos seleccionados

---

## 2. REPORTES PARA PRESENTACIÓN A GERENCIA

### 2.1 Reporte de Justificación de Abastecimiento

**Propósito**: Generar un documento que el encargado de bodega pueda presentar al gerente para justificar las compras propuestas.

**Contenido del Reporte**:

**Sección 1 - Resumen Ejecutivo**
- Total de productos a comprar
- Valor total estimado de la compra
- Resumen por categoría
- Comparativa vs mes anterior

**Sección 2 - Productos Recomendados para Compra**
- Tabla con todos los productos recomendados
- Columnas: Código, Nombre, Categoría, Stock actual, Días de inventario, Cantidad a comprar, Costo unitario, Costo total, Justificación (ejemplo: "Stock crítico", "Alta rotación", "Promoción próxima")
- Resaltar productos en rojo si son urgentes

**Sección 3 - Análisis de Rotación**
- Tabla de rotación por producto
- Productos con mayor rotación (top 20)
- Productos con menor rotación (bottom 10 con justificación de por qué se mantienen)

**Sección 4 - Proyección de Ventas**
- Predicción de salidas para los próximos 30 días
- Comparativa con el stock actual
- Identificación de posibles desabastecimientos

**Sección 5 - Justificación de Transferencias**
- Productos que serán transferidos de otras bodegas en lugar de comprarse
- Ahorro generado por no comprar esos productos
- Stock disponible en bodega origen

**Sección 6 - Anexos**
- Gráficos de salidas históricas
- Predicción de demanda
- Estado de stock actual

**Formato**: PDF con diseño profesional, incluyendo gráficos y tablas claras. Opción de exportar a Excel para edición.

---

### 2.2 Reporte de Productos Candidatos a Transferencia

**Propósito**: Identificar productos que están en una bodega y podrían ser transferidos a otra antes de realizar un pedido.

**Contenido**:

**Sección 1 - Resumen**
- Total de productos con excedente en bodega origen
- Total de productos con déficit en bodega destino
- Valor de inventario que puede ser transferido

**Sección 2 - Tabla de Transferencias Sugeridas**
- Producto
- Bodega Origen (stock disponible)
- Bodega Destino (stock actual)
- Cantidad a transferir
- Días de inventario en destino después de la transferencia
- Motivo: "Excedente en origen", "Déficit en destino", "Baja rotación en origen"

**Sección 3 - Ahorro por Transferencias**
- Monto ahorrado al no comprar esos productos
- Comparativa: costo de compra vs costo de transferencia

**Sección 4 - Prioridad de Transferencia**
- Urgente: productos cuyo déficit en destino es crítico
- Media: productos con déficit moderado
- Baja: productos con excedente que pueden esperar

---

### 2.3 Reporte de Análisis de Stock y Abastecimiento

**Propósito**: Reporte mensual consolidado para gerencia con el estado general del inventario.

**Contenido**:

- **Resumen General**
  - Total de artículos en bodega
  - Valor total de inventario
  - Rotación general
  - Días promedio de inventario

- **Productos Críticos (Stock Bajo)**
  - Lista de productos con stock bajo con sus respectivos niveles
  - Acciones recomendadas (comprar, transferir)

- **Productos con Exceso de Stock**
  - Productos con stock por encima de 90 días de inventario
  - Recomendaciones de promoción o transferencia

- **Comparativa vs Mes Anterior**
  - Evolución del inventario
  - Rotación vs mes anterior
  - Variación en valor de inventario

- **Plan de Compras Propuesto**
  - Productos a comprar
  - Monto estimado
  - Justificación

---

## 3. PANEL DE STATUS DE ARTÍCULOS POR ALMACÉN

### 3.1 Vista de Inventario por Almacén

**Propósito**: Permitir al encargado de bodega ver rápidamente qué artículos tiene cada almacén y su estado actual.

**Descripción**:
- **Tipo**: Tabla con filtros y búsqueda
- **Columnas**:
  - Código de artículo
  - Nombre del artículo
  - Categoría
  - Stock en Bodega 1
  - Stock en Bodega 2
  - Stock en Bodega 3
  - ... (tantas bodegas como existan)
  - Stock Total
  - Punto de Reorden
  - Estado: Crítico, Cerca, Seguro, Exceso

**Filtros**:
- Por bodega específica (para ver solo el stock de una)
- Por categoría
- Por estado (Crítico, Cerca, Seguro, Exceso)
- Por rango de stock (ejemplo: stock < 10 unidades)

**Acciones**:
- Botón "Sugerir Transferencia" en productos con exceso en una bodega y déficit en otra
- Botón "Ver Detalle" para ver historial de salidas del producto

---

### 3.2 Matriz de Transferencias Inteligentes

**Propósito**: Proponer transferencias automáticas entre bodegas basadas en análisis inteligente de stock y rotación.

**Lógica de Transferencia**:

- **Identificar productos con excedente**: Productos cuyo stock supera los 60 días de inventario en una bodega.
- **Identificar productos con déficit**: Productos cuyo stock es menor a 15 días de inventario en otra bodega.
- **Verificar rotación**: Si el producto tiene alta rotación en destino y baja rotación en origen, la transferencia es prioritaria.
- **Calcular cantidad a transferir**: Cantidad necesaria para llevar el stock en destino a 30 días de inventario (sin exceder el excedente en origen).
- **Justificar**: Generar motivo claro (ejemplo: "En bodega origen tiene 120 días de stock con ventas de 5 unidades/mes; en destino tiene 5 días de stock con ventas de 50 unidades/mes")

**Visualización de Sugerencias**:

**Tabla de Transferencias Sugeridas**:
| Producto | Bodega Origen | Stock Origen | Días Inv Origen | Bodega Destino | Stock Destino | Días Inv Destino | Cantidad a Transferir | Prioridad | Acción |
|----------|---------------|--------------|----------------|----------------|---------------|------------------|----------------------|-----------|--------|
| BAT-001 | EL REY | 150 | 45 | ATAHUALPA | 5 | 5 | 50 | Alta | Aprobar |
| REP-003 | ZAMBA | 80 | 60 | EL REY | 10 | 10 | 40 | Media | Aprobar |

**Informe Semanal de Transferencias**: 
- Se genera automáticamente cada semana (5 días antes del fin de mes)
- Contiene todas las transferencias sugeridas para el próximo mes
- Presenta el ahorro estimado por no comprar esos productos
- El encargado de bodega puede aprobar o rechazar cada transferencia

**Regla de Negocio**: Antes de realizar un pedido de compra, el sistema evalúa si el producto existe en otra bodega con excedente y sugiere la transferencia. Esto reduce compras innecesarias y optimiza el inventario global.

---

### 3.3 Proyección de Necesidades antes de Comprar

**Propósito**: Informar al encargado de bodega una semana antes del fin de mes qué productos debe comprar para el próximo mes.

**Contenido del Informe**:

**Sección 1 - Lista de Productos Recomendados para Compra**
- Productos que deberían comprarse basados en:
  - Stock actual menor a 20 días de inventario
  - Proyección de salidas para el próximo mes (basada en histórico y ML)
  - Rotación > 3 veces al año
- Cantidad recomendada a comprar (basada en proyección de 45 días)
- Prioridad (Alta, Media, Baja)

**Sección 2 - Productos que NO deben comprarse** (por tener excedente)
- Productos con stock para más de 90 días
- Productos con baja rotación (< 2 veces al año)
- Recomendación de transferir en lugar de comprar

**Sección 3 - Ahorro Estimado**
- Monto ahorrado al no comprar productos con excedente
- Monto ahorrado por transferencias en lugar de compras

---

## 4. SISTEMA DE NOTIFICACIONES

### 4.1 Notificaciones en el Icono de Campana

El módulo debe tener un icono de notificaciones en la barra superior que muestra alertas relevantes para la bodega.

**Tipos de Notificaciones**:

**🔴 Críticas (Prioridad Alta)**
- "Producto [Nombre] está por debajo del punto de reorden (Stock: X, Punto reorden: Y)"
- "Producto [Nombre] se estima se agotará en 5 días según ML"
- "Bodega [Nombre] tiene 10 productos con stock crítico"
- "El informe semanal de compras está listo (1 semana antes del fin de mes)"

**🟡 Importantes (Prioridad Media)**
- "Producto [Nombre] tiene excedente en Bodega Origen y déficit en Bodega Destino. Transferencia sugerida."
- "Se ha generado reporte mensual de abastecimiento"
- "Rotación de inventario ha disminuido un 10% vs mes anterior"

**🔵 Informativas (Prioridad Baja)**
- "Actualización de inventario completada"
- "Nuevos productos agregados al catálogo"
- "Reporte de stock disponible para descarga"

### 4.2 Reglas de Generación de Notificaciones

| Situación | Cuándo | Mensaje |
|-----------|--------|---------|
| Stock crítico | Stock < punto de reorden | "⚠️ {Producto} tiene stock crítico. Nivel actual: {X}, Punto reorden: {Y}" |
| Predicción de agotamiento | ML predice agotamiento en <7 días | "🔮 {Producto} se agotará en {X} días según predicción. Considerar compra." |
| Excedente en otra bodega | Stock > 60 días en origen y <15 días en destino | "🔄 {Producto} tiene excedente en {Origen} y déficit en {Destino}. Transferir {X} unidades." |
| Reporte semanal listo | 5 días antes del fin de mes | "📋 Reporte de compras sugeridas para próximo mes disponible." |
| Bajo rendimiento | Rotación < 2 veces/año por 3 meses | "📉 {Producto} tiene baja rotación. Considerar promoción o descontinuación." |

---

## 5. FLUJO DE TRABAJO COMPLETO DEL MÓDULO

```
1. ENCARGADO DE BODEGA INGRESA AL MÓDULO
   ↓
2. VISUALIZA DASHBOARD PRINCIPAL
   - KPIs resumen
   - Gráficos de salidas y proyecciones
   - Productos con stock crítico
   ↓
3. REVISA NOTIFICACIONES (Icono de Campana)
   - Productos con stock bajo
   - Productos con predicción de agotamiento
   - Sugerencias de transferencia
   ↓
4. ANALIZA STATUS DE ARTÍCULOS POR ALMACÉN
   - Verifica stock en todas las bodegas
   - Identifica excedentes y déficits
   - Revisa sugerencias de transferencia
   ↓
5. TOMA DECISIONES SOBRE TRANSFERENCIAS
   - Aprobar o rechazar transferencias sugeridas
   - Generar órdenes de transferencia
   - Actualizar inventario después de transferencia
   ↓
6. REVISA INFORME SEMANAL (5 días antes del fin de mes)
   - Productos recomendados para compra
   - Productos con excedente que no deben comprarse
   - Ahorro estimado por transferencias
   ↓
7. GENERA ORDEN DE COMPRA
   - Basada en proyecciones y recomendaciones
   - Justifica cada producto a comprar
   - Presenta al gerente para aprobación
   ↓
8. EXPORTA REPORTE DE JUSTIFICACIÓN
   - PDF con análisis completo
   - Presenta a gerencia con evidencia
   ↓
9. MONITOREA CONTINUAMENTE
   - Stock actualizado en tiempo real
   - Alertas automáticas por notificaciones
   - Dashboard actualizado diariamente
```

---

## 6. REQUERIMIENTOS TÉCNICOS

### 6.1 Fuentes de Datos

| Dato | Fuente | Tabla/Consulta |
|------|--------|----------------|
| Inventario actual | EDW | `fact_inventario_actual` o `kardex` con último movimiento |
| Salidas históricas | EDW | `fact_ventas_detalle` o `fact_movimientos_inventario` con tipdoc='SA' |
| Punto de reorden | Catálogo | `dim_producto.punto_reorden` |
| Costo de productos | Catálogo | `dim_producto.ultcos` |
| Transferencias | EDW | `fact_transferencias` (nueva tabla) |

### 6.2 Modelos de ML Necesarios

| Modelo | Propósito | Frecuencia de reentrenamiento |
|--------|-----------|-------------------------------|
| Predicción de salidas | Predecir cuánto se venderá de cada producto | Mensual |
| Predicción de agotamiento | Predecir cuándo se agotará cada producto | Diario |
| Clasificación de rotación | Identificar productos de alta/baja rotación | Mensual |
| Sugerencia de transferencia | Recomendar transferencias entre bodegas | Semanal |

### 6.3 Cálculos y Fórmulas

| Métrica | Fórmula | Nota |
|---------|---------|------|
| Rotación | Costo de ventas / Inventario promedio | Calcular mensual y anual |
| Días de inventario | (Stock actual / Salidas promedio diarias) × 30 | Salidas promedio últimos 30 días |
| Punto de reorden | (Salidas promedio diarias × Lead time en días) + Stock de seguridad | Configurable por producto |
| Stock de seguridad | Salidas promedio diarias × 5 días (por defecto) | Configurable por producto |

---

## 7. ENTREGABLES DEL MÓDULO

1. **Dashboard de Bodega**: Con todos los gráficos y KPIs descritos en la sección 1
2. **Módulo de Reportes**: Generación de PDF/Excel con justificaciones de abastecimiento
3. **Panel de Status por Almacén**: Vista consolidada de inventario en todas las bodegas
4. **Sistema de Transferencias Inteligentes**: Sugerencias automáticas de transferencias
5. **Sistema de Notificaciones**: Alertas de stock bajo, predicciones y reportes
6. **Informe Semanal de Compras**: Generado 5 días antes del fin de mes
7. **API de Inventario**: Para consultar stock en tiempo real
8. **Modelos de ML**: Predicción de salidas, agotamiento y recomendación de transferencias

---

## 8. FLUJO DE DECISIONES CLAVE

### 8.1 Decisión: ¿Comprar o Transferir?

```
¿Producto tiene stock bajo en bodega A?
   ↓
¿Existe el mismo producto en bodega B con excedente (stock > 60 días)?
   ↓
SÍ → Sugerir transferencia de B a A → Ahorro de costo de compra
   ↓
NO → Sugerir compra a proveedor
```

### 8.2 Decisión: ¿Cuánto Comprar?

```
Calcular stock actual en bodega
   ↓
Calcular salidas promedio diarias (últimos 30 días)
   ↓
Calcular días de inventario = stock / salidas promedio diarias
   ↓
Si días de inventario < 20 → comprar
   ↓
Cantidad a comprar = (salidas promedio diarias × 30 días) - stock actual
   ↓
Redondear a unidades de empaque (ejemplo: cajas de 10 unidades)
```

### 8.3 Decisión: ¿Qué Productos Priorizar?

```
Cada producto tiene:
- Rotación (Alta/Media/Baja)
- Margen (Alto/Medio/Bajo)
- Stock actual (Crítico/Cerca/Seguro)

Orden de prioridad:
1. Alta rotación + Alto margen + Stock crítico
2. Alta rotación + Stock crítico
3. Alta rotación + Alto margen
4. Media rotación + Stock crítico
5. Resto de productos
```

---

## 9. RESUMEN EJECUTIVO

El Módulo Bodega es un sistema integral para la gestión de inventario que permite al encargado de bodega tomar decisiones basadas en datos históricos y machine learning. Los componentes clave son:

1. **Dashboard con KPIs y gráficos** que muestran el estado del inventario, productos con stock bajo, rotación y proyecciones de salidas
2. **Panel de status por almacén** que permite ver el stock de cada artículo en todas las bodegas y gestionar transferencias inteligentes
3. **Sistema de notificaciones** que alerta sobre productos con stock crítico, predicciones de agotamiento y transferencias sugeridas
4. **Reportes para gerencia** que justifican las decisiones de abastecimiento y compras propuestas
5. **Flujo de trabajo optimizado**: primero transferir entre bodegas, luego comprar lo que realmente se necesita, basado en proyecciones de ventas

El módulo asegura que la bodega siempre tenga stock de los productos que se venden, evitando desabastecimientos y reduciendo compras innecesarias de productos con baja rotación.