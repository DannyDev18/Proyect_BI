-- Extracción de la tabla clientes (Dimensión Cliente)
-- Auditoría 41: tipo_id/nombre_clase/nombre_zona/dias_credito/sexo llegaban hardcodeados
-- (constantes fijas para el 100% de los clientes) pese a que SAP tiene el dato real y
-- poblado -- tiprucced (tipo real de identificación), clasesclientes.nomcla (nombre real
-- de clase vía codcla), zona.nomzona (nombre real de zona vía codzona), clientes.codcre
-- (plazo de crédito real, NULL en el 98.4% de los casos -- no 30 para todos) y
-- clientes.sexo (columna real, no una columna derivada).
SELECT
    c.codemp,
    c.codcli,
    c.nomcli AS nombre_cliente,
    c.rucced AS ruc_cedula,
    c.tiprucced AS tipo_id,
    c.codcla AS clase_cliente,
    cc.nomcla AS nombre_clase,
    c.codzona AS zona,
    z.nomzona AS nombre_zona,
    c.ciucli AS ciudad,
    c.cupo AS limite_credito,
    c.codcre AS dias_credito,
    c.estado,
    c.sexo,
    c.fecult
FROM
    clientes c
    LEFT JOIN clasesclientes cc ON cc.codemp = c.codemp AND cc.codcla = c.codcla
    LEFT JOIN zona z ON z.codemp = c.codemp AND z.codzona = c.codzona
WHERE
    c.codemp = '{CODEMP}';
