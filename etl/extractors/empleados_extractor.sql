-- Extracción de la tabla nom_empleados (Dimensión Empleado)
SELECT 
    codemp,          -- Código de empresa
    codnom AS codemple,        -- Código del empleado
    nombre AS nombre_empleado, -- Nombre completo
    rucced AS cedula,          -- Cédula de identidad
    cargo,           -- Cargo que ocupa
    coddepar AS departamento, -- Departamento
    sueldo AS sueldo_base, -- Sueldo base
    fecha_ing AS fecha_ingreso, -- Fecha de ingreso
    activo           -- Estado activo/inactivo (1 o 0, mapeado a boolean)
FROM 
    nom_empleados
WHERE 
    codemp = '01';
