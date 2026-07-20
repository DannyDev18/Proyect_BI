# Informe de revisión — Capítulos I-IV + Referencias (borrador completo)
Fecha: 2026-07-17 | Norma: APA 7 | Contra: memoria del proyecto (`docs/tesis/memoria_tesis.md`) + formato UTA (`docs/ejemplo_tesis/tesis ejemplo.md`)

## Resumen ejecutivo

El borrador es sólido en su núcleo: sin fabricación de datos ni referencias, cadena objetivos→metodología→resultados→conclusiones consistente en contenido, y todas las citas en texto tienen su entrada en `referencias.md` (y viceversa). El problema dominante es estructural, no de contenido: la jerarquía de encabezados Markdown está rota en los Capítulos I y II (subsecciones marcadas al mismo nivel que su sección padre), lo que romperá cualquier índice generado automáticamente o conversión a LaTeX. El segundo problema es de completitud esperada: faltan preliminares (portada, aprobación, dedicatoria, resumen ejecutivo/abstract) y Anexos, ya señalados como pendientes en las notas de trazabilidad de cada capítulo, por lo que no se cuentan aquí como hallazgo nuevo sino que se listan en Recomendaciones generales.

## Errores críticos (bloquean la entrega/defensa)

| # | Ubicación | Problema | Recomendación |
|---|---|---|---|
| 1 | `01_marco_teorico.md:7` | `## 1.1.1 Planteamiento del problema` usa el mismo nivel de encabezado (`##`) que su sección padre `## 1.1` (línea 3), rompiendo la jerarquía del documento. Contrasta con el resto del mismo capítulo, donde 1.3.x/1.4.x sí usan `###` correctamente bajo 1.3/1.4. | Cambiar la línea 7 a `### 1.1.1 Planteamiento del problema`. |
| 2 | `02_metodologia.md:11,25,33,49,66` | Las cinco subsecciones (2.1.1, 2.2.1, 2.2.2, 2.2.3, 2.2.4) están marcadas como `##` en vez de `###`, quedando al mismo nivel que 2.1/2.2. Todo el capítulo tiene la jerarquía plana. | Cambiar las 5 líneas de `##` a `###`. Verificar que no queden como capítulos de primer orden en un índice generado. |

## Errores mayores (afectan la calidad, no bloquean)

| # | Ubicación | Problema | Recomendación |
|---|---|---|---|
| 3 | `02_metodologia.md` §2.2 / `03_resultados.md` §3.3 | El método de diseño del Data Warehouse (Kimball) se anuncia en Metodología pero su desarrollo completo (dimensiones, hechos, matriz de bus) se remite a Resultados 3.3. Un lector que solo revise el Capítulo II no encuentra "cómo" se diseñó el DW, solo una promesa de que se explicará después. La nota de trazabilidad del propio capítulo ya justifica esta decisión con la estructura UTA, pero el cuerpo entregable no se lo explica al lector. | Agregar una frase explícita en 2.2 (cuerpo, no solo nota interna) del tipo: "El detalle del modelado dimensional resultante se presenta en el apartado 3.3, siguiendo la convención de esta estructura de tesis donde el diseño de la arquitectura se documenta como resultado." |
| 4 | `02_metodologia.md` Tabla 2.1 vs `03_resultados.md` §3.8.1 | La cifra de `fact_ventas_detalle` aparece como "~539 000" (redondeada) en la Tabla 2.1 y como "538 862" (exacta) en 3.8.1, sin que el lector sepa que son la misma fuente en dos niveles de precisión. No es una contradicción numérica real, pero puede leerse como inconsistencia a primera vista. | Unificar: usar la cifra exacta (538 862) también en la Tabla 2.1, o anotar explícitamente "cifra aproximada; ver cifra exacta en 3.8.1". |
| 5 | `03_resultados.md` §3.4.4 | La sección de "Interfaz web" es la más breve de todo 3.4 (un solo párrafo genérico) frente al objetivo específico 6 ("Desarrollar dashboards web interactivos... que integren los KPI y las predicciones"), que promete un desarrollo más rico. El capítulo de Resultados no muestra evidencia concreta (qué ve cada rol, qué predicciones se integran en qué pantalla) de ese objetivo cumplido. | Ampliar 3.4.4 con al menos un párrafo por rol (o una tabla dashboard↔rol↔indicadores) antes de la entrega final, o remitir explícitamente a capturas de pantalla en Anexos si se agregan. |

## Errores menores (forma, estilo, detalles)

| # | Ubicación | Problema | Recomendación |
|---|---|---|---|
| 6 | `04_conclusiones.md`, recomendación 2 | Cita "AUC-ROC de 0.929" de Fauzi et al. (2026) como dato específico, cifra que no aparece registrada en la Bibliografía canónica de la memoria (solo constan 84.88 % de exactitud y AUC-ROC de 92.94 %, que en escala 0-1 equivaldría a 0.9294, no 0.929 — son consistentes en valor pero el formato decimal difiere ligeramente y no está marcado como el mismo dato). | Unificar el formato: usar 0.9294 (o "92.94 %") de forma idéntica a como se citó en 1.2, para que quede claro que es el mismo dato y no uno nuevo sin verificar. La propia nota de trazabilidad del capítulo ya señala esto — falta solo aplicar la corrección. |
| 7 | Los 4 capítulos | Uso consistente y correcto de "et al." a partir de 3+ autores en narrativa, y de "y"/"&" según posición (narrativa/parentética) conforme a APA 7 en español. Sin errores detectados en este punto — se documenta como verificación positiva, no como hallazgo. | Ninguna acción. |
| 8 | `03_resultados.md` §3.5 | Los tres defectos reales corregidos se narran en prosa corrida sin tabla ni identificador, dificultando su referencia cruzada desde Conclusiones/Recomendaciones si se quisiera citar uno específico más adelante. | Opcional: convertir a una tabla breve (defecto / causa / corrección) si el formato final lo admite. |

## Recomendaciones generales

1. **Prioridad 1 (antes de cualquier otra cosa):** corregir la jerarquía de encabezados (hallazgos 1 y 2) — es mecánico, rápido, y bloquea la generación de cualquier índice o conversión a LaTeX.
2. **Prioridad 2:** cerrar el hallazgo 5 (ampliar evidencia de dashboards) antes de dar el Capítulo III por definitivo, porque es el objetivo específico con menos evidencia concreta en el texto actual.
3. **Prioridad 3:** unificar cifras (hallazgos 4 y 6) — coherencia numérica, rápido de aplicar.
4. **Pendiente conocido (no es hallazgo nuevo, ya está señalado por los propios capítulos):** faltan los preliminares (portada, aprobación del tutor, autoría, derechos de autor, dedicatoria, agradecimiento, resumen ejecutivo, abstract) y los Anexos; no se han generado capturas de pantalla ni diagramas de arquitectura como figuras. Ninguno de estos bloquea seguir escribiendo, pero sí bloquean una entrega formal.
5. Antes de la defensa, recalcular contra el EDW real las cifras marcadas como "aproximadas" o con fecha de corte (`SELECT COUNT(*)` sobre `fact_ventas_detalle`, y confirmar si los modelos de demanda/segmentación/churn/anomalías (`docs/ml_metrics_report.md`) se reentrenaron después de julio de 2026).

## Evaluación

| Dimensión | Nivel |
|---|---|
| Estructura | Deficiente (por los hallazgos 1-2, mecánicos pero reales; el resto del documento sí sigue el orden esperado) |
| Redacción | Bueno |
| Gramática y ortografía | Excelente (sin errores detectados en la revisión) |
| Norma de citación (APA 7) | Excelente (10/10 citas en texto con entrada en referencias y viceversa; formato narrativa/parentética correcto) |
| Coherencia y consistencia | Bueno (2 inconsistencias numéricas menores, hallazgos 4 y 6) |
| Cadena metodológica (objetivos↔metodología↔resultados↔conclusiones) | Bueno (7/7 objetivos con evidencia en Resultados y conclusión correspondiente; objetivo 6 con evidencia más débil, hallazgo 5) |
| Resultados (procedencia de cifras) | Excelente (toda cifra cuantitativa remite a un archivo real del repositorio, documentado en las notas de trazabilidad) |

**Cumplimiento estimado: 78 %.** Cálculo: 7 dimensiones ponderadas por igual (≈14.3 % cada una); Estructura se computa como 40 % de su peso (2 errores críticos concretos y mecánicos, fácilmente subsanables, no reflejan mal trabajo de fondo) y el resto de dimensiones entre 85 % y 100 % de su peso según la tabla. El número refleja que el contenido intelectual del documento está casi completo y correcto, pero el documento no está listo para entregarse tal cual por los defectos de formato/estructura y las secciones aún pendientes fuera de este alcance (preliminares, anexos).

**Prioridad de trabajo sugerida:** (1) corregir encabezados → (2) ampliar 3.4.4 → (3) unificar cifras → (4) redactar preliminares y Anexos como capítulos aparte cuando el usuario lo indique.
