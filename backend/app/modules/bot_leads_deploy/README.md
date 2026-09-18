# Bot Leads Deploy - Backend

Esta carpeta es el punto de trabajo para cambios de Leads Deploy. Los archivos aquí son copias físicas separadas de Nuevos Productos para que podamos evolucionarlos sin editar el bot estable.

Los lotes ejecutan una fila a la vez y comparten un navegador desde la validación
previa hasta la última verificación. `browser_session.py` conserva el contexto,
las cookies y una pestaña por función (UTEL, InConcert y Balanceador). UTEL navega
al siguiente programa en su misma pestaña; los CRM reutilizan los listados cuando
están disponibles y autenticados. Los popups de detalles se cierran al comenzar
la siguiente fila, después de guardar su evidencia.

Las pausas existentes entre tandas permanecen activas con el navegador abierto.
Al terminar se respeta `keep_browser_open`; al cancelar o apagar el backend se
liberan los recursos. Un segundo lote de Leads Deploy espera su turno antes de
usar el perfil. Los reintentos del módulo también conservan el navegador elegido.
Esto evita aperturas y navegaciones redundantes, sin garantizar acceso a sitios
que estén bloqueando el tráfico de QA.
