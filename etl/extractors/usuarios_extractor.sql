-- Extracción de la tabla usuarios (Dimensión Usuario)
SELECT 
    codemp,          -- Código de empresa
    codusu,          -- Código de usuario único
    nomusu AS nombre_usuario, -- Nombre del empleado tras la cuenta
    gruusu AS rol,            -- Rol o perfil de acceso (grupo de usuario)
    'A' AS estado             -- Estatus del usuario por defecto 'A'
FROM 
    usuarios
WHERE 
    codemp = '{CODEMP}';
