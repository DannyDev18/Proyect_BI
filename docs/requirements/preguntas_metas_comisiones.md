# Preguntas de Levantamiento de Requerimientos: Módulo de Metas y Comisiones

Este cuestionario sirve como guía estructurada para entrevistar a los responsables del área de ventas, contabilidad y gerencia general. Las respuestas definirán la arquitectura lógica del sistema de incentivos en la plataforma de BI.

---

### **1. Definición y Asignación de Metas**

- **¿Cuál es la variable principal sobre la que se mide la meta?** ¿Se calcula en montos monetarios (dólares netos), en cantidades de productos físicos vendidos, o en porcentaje de margen/utilidad generada?
- **¿A qué nivel se asigna la meta?** ¿Es individual por vendedor, global por sucursal/bodega, o se maneja un modelo híbrido (ej. si la sucursal llega al 100%, se libera el bono individual)?
- **¿Qué criterios se usan como base para calcular la meta inicial?** ¿Se toma el histórico de ventas del mismo mes del año anterior? ¿Se añade un porcentaje de crecimiento global impuesto por la empresa (ej. +5%)? ¿Se considera la estacionalidad?

### **2. Lógica e Incentivos de Comisiones**

- **¿Cómo se calcula la comisión base?** ¿Es un porcentaje plano sobre el total de ventas del vendedor (por cada venta), o solo empieza a comisionar a partir de un porcentaje determinado de su meta (ej. comisiona solo si llega a más del 70% de cumplimiento)?
- **¿El porcentaje de comisión varía según la categoría del producto (clase)?** Por ejemplo, ¿los repuestos de alta rotación pagan una tasa menor que los repuestos OEM de alto margen?
- **¿Cómo funciona el sobrecumplimiento?** Si un vendedor supera el 100% de su meta, ¿recibe un bono fijo, o su porcentaje de comisión sube retroactivamente sobre toda la venta?

### **3. Ciclo de Vida y Flujo de Aprobación**

- **¿Cuál es el proceso habitual de propuesta y validación?** ¿El administrador de TI/ETL genera las propuestas basadas en la estimación del modelo de Machine Learning, el Gerente de Ventas las ajusta/aprueba y luego se "congelan" al iniciar el mes?
- **¿Hasta qué día del mes en curso se permite realizar modificaciones presupuestarias o ajustes manuales a las metas sin alterar el historial auditado?**

### **4. Reglas Especiales y Excepciones**

- **¿Qué ocurre si un vendedor es transferido de sucursal a mitad de mes?** ¿Su meta se divide proporcionalmente por los días laborados en cada almacén o se le evalúa sobre la sucursal de origen?
- **¿Qué transacciones no suman a la meta?** ¿Las devoluciones de mercancía o notas de crédito restan a la meta acumulada del mes en curso, o afectan directamente la comisión base calculada?
- **¿Existen topes de comisión?** ¿Hay un límite máximo de dinero que un vendedor puede comisionar en un solo mes o es ilimitado?
