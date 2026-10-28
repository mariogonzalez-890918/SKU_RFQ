> Documento de diseño previo. El alcance implementado y las decisiones posteriores del usuario se encuentran en [IMPLEMENTACION.md](IMPLEMENTACION.md). Razones sociales dinámicas: solo AUXTI y Superadministrador administran sus vínculos con las cuatro sucursales.

# Integración técnica, entrega y aceptación

## Base inspeccionada

Análisis sobre **1.8.0**, commit `10d47560fcbf057f5118cb444ddd78ad412e558d`. El código es la referencia para comportamientos actuales; algunos párrafos históricos del README aún describen restricciones anteriores.

| Pieza actual | Hallazgo y uso propuesto |
| --- | --- |
| `sku-servidor/server.py` | HTTP con Python, SQLite, sesiones, CSRF, roles y rutas. `Store` crea `users`, `role_modules` y alcances de requisiciones; `manage_user` valida una lista cerrada de roles. Reutilizar autenticación, agregar autorización comercial central sin basarla solo en menús. |
| `permissions.py` | `ventas` significa generador SKU Ventas; el acceso de Requisición está restringido expresamente. Introducir claves comerciales nuevas sin reutilizar `ventas` para pedidos ni eliminar ese aislamiento. |
| `ventas.py` | `SalesStore` guarda catálogo SKU en JSON versionado, conserva históricos validados y protege columna A. `import_master` agrega/omite existentes: no es un importador comercial de precios/clientes/pedidos. |
| `sku/erp-ui.js`, `navigation-ui.js` | Navegación y submenús actuales adaptables. Agregar selector/adaptador hacia los módulos nuevos, con barra y vistas cercanas a Odoo 14. No reescribir de golpe requisiciones. |
| `reportes.py`, `reporte_export.py` | Valuación decimal, filtros y exportación de requisiciones. En 1.8.0 se compara requisitado/surtido y se costea el surtido real. Reutilizar utilidades, no mezclar esos hechos con ventas comerciales. |
| `autorizaciones.py`, `aprobaciones_admin.py` | Flujos de corrección/cancelación y autorizaciones de Sistemas. Incorporar un dominio comercial con sus propias acciones y alcances; no disfrazar ventas como requisiciones. |
| `ticket.py` | Impresión Bixolon de 80 mm existente. Extraer primitivas de layout e impresión, manteniendo los contenidos y permisos propios de cada documento. |
| `respaldos.py` | Respalda SKU Compras, SKU Ventas y un conjunto cerrado de tablas de requisiciones. No cubre futuras tablas comerciales: debe ampliarse explícitamente. |
| `tools/build_public.py`, `sku/SKU-JAD-Servidor.spec` | Lista de archivos y empaquetado del EXE. Incluir módulos futuros expresamente, validar una instalación vacía y una migrada, sin credenciales ni datos reales en Releases. |

Los directorios de otros proyectos del workspace, como `ventas-test`, no pertenecen al código publicado de SKU_RFQ; no se reutilizan ni se incluyen automáticamente.

## Modelo propuesto

Extender la misma `data/sku.sqlite3` con tablas comerciales normalizadas, claves foráneas, índices y migraciones versionadas. No introducir una segunda base sin coordinación de respaldos y transacciones.

| Entidad | Responsabilidad |
| --- | --- |
| `companies`, `company_products` | Tres emisores capturados por el usuario y disponibilidad comercial del SKU por razón social/canal. |
| `commercial_products` | ID comercial durable, SKU único/inmutable, vínculo al registro SKU, unidad y atributos de venta. El ID comercial no depende del número de fila de Excel ni de un ID de catálogo recreado por un reinicio. |
| `commercial_customers`, `customer_company`, `customer_access` | Clientes y asignaciones/cartera, con referencias comerciales estables. |
| `price_lists`, `price_rule_versions`, `price_list_access` | Listas y reglas versionadas por razón social, canal, sucursal/caja y cliente; IVA 0/8/16 % congelado en líneas. |
| `quote_templates`, `quote_template_lines` | Plantillas y secciones/notas, versionadas. |
| `sales_documents`, `sales_lines`, `sales_revisions` | Presupuesto/pedido, referencias entre documentos y snapshots de cada línea. |
| `pos_configs`, `pos_sessions`, `pos_orders`, `pos_lines`, `pos_payments`, `cash_movements` | Caja, sesión, venta, cobros y conciliación; separar importes cobrados de efectivo recibido/cambio. |
| `commercial_targets` | Metas comerciales, únicamente si se confirma ese alcance. |
| `commercial_user_access`, `role_capabilities` | Razones sociales, sucursales, cajas/carteras y capacidades comerciales. No sobrecargar `user_requisition_access`. |
| `commercial_approvals`, `commercial_audit`, `commercial_sequences` | Excepciones, historial y folios por emisor/tipo/sucursal/caja, sin reutilización; inicial institucional configurable y folio interno de Expendios. |

Razón social emisora, productos, precios, IVA 0/8/16 %, moneda, unidad, cliente y condiciones utilizados se congelan en el documento confirmado. Los cambios posteriores del maestro no recalculan ventas pagadas. Mantener importes con `Decimal`/texto decimal canónico, nunca `float` como valor de negocio. Guardar fecha del servidor y fecha de negocio/sesión según regla declarada; no permitir editar la fecha original para alterar indicadores.

### Capacidades y rutas propuestas

`comercial_ventasins` y `expendios` son módulos distintos del actual `ventas`. Capacidades propuestas: `consultar`, `presupuestar`, `confirmar_pedido`, `operar_caja`, `reportes`, `importar_productos`, `importar_layout`, `administrar_precios`, `autorizar_excepciones`. **Ver Expendios / Punto de Venta** se edita por perfil; sucursales/cajas se asignan por usuario. Solo Superadministrador cambia la matriz, como en el sistema actual.

Rutas nuevas bajo `/api/comercial/...` y `/api/expendios/...`; por ejemplo presupuestos/confirmar, pedidos, productos, listas, cajas, sesiones/abrir, ventas/cobrar y reportes. Cada ruta y descarga valida sesión, módulo, capacidad, razón social, alcance y revisión. Cancelar Expendios requiere además rol AUXTI o Superadministrador; Gerencia queda excluida. No basta que un botón esté oculto. Las impresiones consultan el documento ya autorizado por ID; no aceptan un total arbitrario enviado por el cliente.

### Transacciones y concurrencia

- Folios, snapshots y transición de presupuesto a pedido se confirman en una transacción corta con control de revisión.
- Unicidad para clave de idempotencia por usuario/operación y para sesión activa por caja, conforme a la política que se apruebe.
- Venta, pagos y folio se guardan juntos; impresión y generación de archivos suceden después de confirmar. Si la respuesta se pierde, consultar el resultado por la misma clave antes de reintentar.
- Cierre usa revisión/estado de sesión y concilia efectivo: fondo + cobros en efectivo − reembolsos en efectivo + entradas − retiros. No sumar tarjeta al cajón ni sumar el efectivo recibido sin descontar cambio.
- La primera entrega comercial requiere conexión al servidor. No prometer caja sin conexión, sincronización entre servidores o impresión silenciosa: exigen cola, conciliación y resolución de conflictos específicas.

## Migración y respaldos

1. Registrar versión de esquema y respaldo previo consistente. Migraciones aditivas con transacción; no reconstruir usuarios ni reemplazar catálogos con archivos iniciales.
2. Registrar perfiles/capacidades sin crear cuentas. Nuevos módulos apagados para perfiles existentes, salvo Superadministrador. Conservar revocaciones y alcances actuales de 1.8.0.
3. Vincular catálogo comercial por SKU existente e identidad durable. SKU histórico inválido/ambiguo se reporta, no se regenera ni se “corrige” automáticamente.
4. Activar VentasIns y luego Expendios por sucursal piloto mediante configuración; los demás módulos continúan disponibles.
5. Ampliar respaldo con un paquete comercial consistente que incluya catálogo comercial, clientes, listas, documentos, caja, pagos y auditoría. Restaurar dominios dependientes juntos; no restaurar solo pagos o precios sobre pedidos de otra revisión.
6. Bloquear vaciado de SKU Ventas si rompe referencias comerciales, o exigir un plan conjunto validado que preserve identidades. Mantener máximos de folios y claves de cobro/idempotencia para no reutilizar números ni duplicar pagos después de una restauración.
7. Reversión: un EXE 1.8.0 no debe abrir y escribir una base migrada a 2.0. Restaurar una copia previa en un entorno separado; no reemplazar sin más el EXE después de registrar nuevas ventas.

No se deducen existencias ni costos de productos terminados a partir de requisiciones de insumos. Si se requiere inventario real del expendio, reservar/descargar stock, producción o enlace entre compras y venta, se definirá el modelo correspondiente antes de activar ese comportamiento.

## Etapas propuestas

| Etapa | Resultado revisable | Condición de salida |
| --- | --- | --- |
| A | Este análisis, menús, layout y prototipo visual. | Comentarios del PR incorporados; definiciones pendientes acordadas. |
| B | Productos comerciales, clientes, precios, importaciones y accesos. | SKU históricos intactos; cargas idempotentes y aisladas por alcance. |
| C | Presupuestos, plantillas, pedidos e impresiones. | Conversión única, snapshots de precios y autorización comercial probadas. |
| D | Expendios/TPV, caja, pagos y ticket Bixolon. | Cobro único, cierre conciliado y piloto físico de impresión. |
| E | Dashboard, metas aprobadas, exportaciones, migración y EXE 2.0. | Restauración/migración y regresiones completas, más aceptación por sucursal piloto. |

Se agrega un [presupuesto preliminar de 200–320 horas efectivas](ESTIMACION.md) para el alcance completo, incluidos tres emisores, clientes, IVA y cancelaciones. No constituye una fecha comprometida; se revisa con los volúmenes y el primer piloto.

## Criterios de aceptación para implementación

| Área | Evidencia exigida |
| --- | --- |
| Integración | Un inicio de sesión y el mismo EXE. SKU y requisiciones de 1.8.0 siguen funcionando, incluido costeo real, autorizaciones y Bixolon. |
| Expendios por perfil | Deshabilitar su checkbox oculta la aplicación y devuelve denegación en API, impresión, exportación y apertura directa de caja. Habilitar solo consulta no permite cobrar. |
| Multirrazón | Tres emisores vacíos capturados por el usuario; pedidos/cajas/folios/impresión aislados; consolidado solo de emisores autorizados y sin mezclar monedas. |
| IVA | Probar 0/8/16 % mixtos, precios incluidos/excluidos y descuentos: base 300.00 + IVA 24.00 = total 324.00 en el caso de prueba. |
| Folios y cancelación | Inicio institucional elegido, folio interno y solicitud en Expendios; AUXTI/Superadministrador autorizan, Gerencia no; preservar caja hasta registrar devolución real. |
| Clientes y exportación | Alta y direcciones por cartera/emisor; seleccionar columnas, guardar plantillas y exportar todas las filas del filtro sin recuperar accesos revocados. |
| Alcances | Un usuario de EJIDOS no ve ni opera cajas/tickets de SAN PABLO. Un VentasIns no accede a documentos de otra cartera mediante IDs o exportaciones. Requisición no obtiene costos comerciales. |
| Precios | Mismo SKU con precio distinto por canal/sucursal/cliente/vigencia; servidor selecciona regla; cambio de precio no modifica un ticket histórico. Precio faltante bloquea cobro. |
| Importación | SKU con ceros intactos, duplicados/ambigüedades detectados, vista previa obligatoria, cambios concurrentes rechazados y ningún borrado por omisión de filas. |
| Cobro | Doble clic, dos pestañas y reintento tras pérdida de respuesta producen un solo cobro/folio. Un fallo al imprimir permite reimprimir sin cobrar de nuevo. |
| Anulación/devolución | Autorización con motivo y movimiento compensatorio; no borrar ventas pagadas. Sin autoaprobar una excepción propia. |
| Dashboard | Presupuesto, pedido, ticket y cobro vinculados no duplican ingresos; fechas, devoluciones, anticipos, impuestos y monedas se identifican. Metas usan una métrica explícita. |
| Impresión | Documento/PDF/ticket concuerdan con el servidor; prueba de Bixolon física de 80 mm en equipo cliente; textos largos, muchas líneas, copia y firmas no se cortan. |
| Visual y móvil | Comparativa de las siete pantallas acordadas con referencias Enterprise 14; teclado/foco, contraste y funcionamiento a escritorio/tablet/celular. Menú se cierra con Escape y conserva navegación. |
| Migración/restore | Base 1.8.0 migra sin perder usuarios, SKU, contraseñas, requisiciones o máximos de folios; respaldo comercial se restaura junto con dependencias; no se reutilizan cobros. |
| Rendimiento | Medir búsqueda y confirmación con el volumen real y terminales concurrentes. Objetivos preliminares en LAN: búsqueda p95 <500 ms y confirmación p95 <2 s, fuera de impresión; validar en hardware piloto, no prometerlos por diseño. |

## Validación de este PR documental

Revisar enlaces relativos, ausencia de recursos externos en el prototipo, navegación por perfil, checkbox de visibilidad de Expendios, menús, listas/formulario, TPV y previsualizaciones de documento/ticket. Confirmar que el diff solo contiene documentación y la excepción de `.gitignore`; no modifica fuentes de la aplicación, versión, esquemas, datos, requisitos de ejecución ni workflow de Releases. No corresponde recompilar el EXE ni ejecutar pruebas de cobro reales para aprobar este análisis.
