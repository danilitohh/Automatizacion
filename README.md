# QA Automation Desktop

Aplicación desktop para centralizar automatizaciones de QA. Esta primera entrega implementa la **Fase 1**: shell de Electron, dashboard, backend FastAPI local, SQLite, logs diarios, configuración y comunicación segura entre procesos.

Las automatizaciones reales de formularios, monitoreo visual y Excel/Strapi se incorporarán en las fases siguientes. En esta etapa la interfaz deja los módulos preparados y no usa URLs ni datos reales.

## Arquitectura

```text
Electron (frontend)
    ↓ HTTP local
FastAPI (backend)
    ↓
SQLite + logs organizados
```

Electron arranca FastAPI automáticamente cuando se inicia la aplicación. El renderer no tiene acceso a Node ni a secretos. Las credenciales futuras se leerán únicamente desde `.env` en el backend.

## Requisitos

- Node.js 18 o superior y npm.
- Python 3.11 o superior.
- En Windows, el comando `python` debe estar disponible. Se puede usar otro con `PYTHON_COMMAND`.

## Instalación

Desde la raíz del proyecto:

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

No completes todavía las variables de CRM o Strapi con credenciales reales; esos módulos pertenecen a fases posteriores.

## Ejecución

### Opción recomendada: Electron + FastAPI

```powershell
npm run dev
```

El proceso principal de Electron intentará arrancar FastAPI en `http://127.0.0.1:8000` y abrirá `frontend/index.html`.

### Ejecutar FastAPI por separado

Es útil para revisar la API o depurar el backend:

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

La documentación interactiva queda disponible en `http://127.0.0.1:8000/docs`.

## Endpoints de la Fase 1

| Método | Endpoint | Uso |
| --- | --- | --- |
| GET | `/api/health` | Comprueba que FastAPI está disponible. |
| GET | `/api/dashboard/summary` | Métricas del día y última ejecución. |
| GET | `/api/executions?limit=20` | Historial reciente. |

## Tests

```powershell
python -m pytest backend/tests -q
```

Los tests usan archivos SQLite temporales y no modifican la base de datos local.

## Estructura importante

```text
frontend/                 Interfaz Electron y renderer.
backend/app/api/          Rutas HTTP.
backend/app/config/       Variables y rutas centralizadas.
backend/app/database/     Conexión y consultas SQLite.
backend/app/services/     Reglas del dashboard y logging.
backend/tests/            Pruebas del backend.
storage/logs/             Logs organizados por fecha.
storage/reports/          Reportes futuros.
storage/screenshots/      Evidencias futuras.
storage/visual_comparisons/ Comparaciones futuras.
docs/                     Decisiones de arquitectura.
```

## Prueba manual de la Fase 1

1. Ejecuta `npm run dev`.
2. Comprueba que la ventana muestra el dashboard y el indicador **Backend conectado**.
3. Confirma que las tarjetas comienzan en cero y que aparece el estado de SQLite.
4. Navega entre Formularios, Monitoreo visual, Excel vs Web, Historial y Configuración.
5. Pulsa el botón de actualizar y confirma que el timestamp cambia.
6. Abre `/docs` en un navegador si quieres inspeccionar el contrato de FastAPI.
7. Revisa `storage/logs/YYYY-MM-DD/backend.log` para comprobar el log de inicio y las consultas.

## Configuración y seguridad

`.env.example` documenta las variables esperadas. `.env` está ignorado por Git y nunca debe subirse. El token de Strapi y la contraseña del CRM nunca se expondrán al frontend: FastAPI será el único componente que hablará con esos servicios.

## Cómo añadir una automatización después

Cada automatización tendrá su propio módulo dentro de `backend/app/automations/`, sus esquemas y su servicio. El servicio guardará una fila en `executions` y la interfaz podrá consumir su resultado mediante un endpoint específico. La Fase 2 comenzará con `forms/`; la Fase 3 con `visual_monitoring/`; la Fase 4 con `excel_strapi/`.

## Problemas frecuentes

- **Backend desconectado:** instala `backend/requirements.txt`, verifica que Python está en el PATH y revisa la consola de Electron.
- **El puerto 8000 está ocupado:** inicia FastAPI en otro puerto y ajusta `API_PORT` y `API_URL` de forma coherente; en una mejora posterior se automatizará esta negociación.
- **La ventana no abre:** ejecuta `npm install` y comprueba la versión de Node.
- **No aparecen logs:** verifica que el proceso tenga permisos de escritura en `storage/`.

## Próxima fase

Antes de avanzar a la Fase 2 hay que verificar esta base con los tests y la prueba manual. La próxima entrega añadirá una validación sencilla de formularios con Playwright, sin asumir selectores, CRM o URLs reales.
