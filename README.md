# QA Automation Desktop

Aplicación desktop para centralizar automatizaciones de QA. Esta primera entrega implementa la **Fase 1**: shell de Electron, dashboard, backend FastAPI local, SQLite, logs diarios, configuración y comunicación segura entre procesos.

Las automatizaciones reales de formularios, monitoreo visual y Excel/Strapi se incorporarán en las fases siguientes. También se añadió el módulo **Bot de formularios**, que permite definir scripts paso a paso y ejecutarlos con Playwright en segundo plano.

El módulo **PDP vs documentos** compara las páginas de producto con un Excel de URLs y un DOCX de referencia. Revisa título, descripción, asignaturas y preguntas frecuentes, y guarda el reporte en `storage/reports/pdp/`.

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
python -m playwright install chromium
```

Para usar Google Chrome con una sesión persistente de QA, abre el perfil aislado con:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\open_chrome_qa.ps1
```

Las ejecuciones usan Chromium en modo headless por defecto. Si necesitas una sesión persistente, selecciona **Google Chrome - Perfil QA**; las cookies se guardan en `storage/browser_profiles/chrome-qa`, que está excluida de Git.

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
| POST | `/api/bots/run` | Ejecuta un flujo web con Playwright y guarda sus evidencias. |

## Validar PDP vs DOCX

1. Abre **PDP vs documentos** en la navegación.
2. Sube el Excel, con una columna de programa (`Programa`, `Carrera` o `Nombre`) y una URL (`URL`, `Link`, `Enlace` o `PDP`).
3. Sube el documento `.docx`. Si contiene varios programas, inicia cada bloque con el nombre del programa como título y usa encabezados como **Descripción**, **Asignaturas** y **Preguntas frecuentes**.
4. Pulsa **Comparar PDPs**. La aplicación revisa cada URL, muestra la coincidencia por sección y registra el resultado en el historial.

La comparación es textual y tolera cambios menores de redacción. Las diferencias marcadas como **Revisar** requieren verificación humana, especialmente si el contenido de la PDP está dentro de acordeones, imágenes o componentes sin texto HTML.

## Proveedores de IA

Las integraciones de Ollama Cloud, Groq y Gemini viven en `backend/app/services/ai_service.py`. Sus claves se configuran únicamente en `.env`; el renderer solo puede consultar el estado booleano mediante `GET /api/ai/providers`.

Para las automatizaciones futuras se dispone de `POST /api/ai/generate` con `provider`, `prompt`, `system_instruction` opcional y `model` opcional. La respuesta tiene el mismo formato para los tres proveedores.

### Respaldo automático

El módulo PDP semántico utiliza esta cascada: **Gemini → Groq → Ollama local → comparador determinístico**. Si un proveedor responde con cuota agotada, error de red o una respuesta inválida, se registra el motivo y se intenta el siguiente. Si todos fallan, la comparación textual continúa y los casos ambiguos quedan para revisión manual.

Para activar Ollama local:

1. Instala Ollama y descarga el modelo definido en `OLLAMA_LOCAL_MODEL` (por defecto `gpt-oss:20b`).
2. Confirma que el servidor local esté disponible en `OLLAMA_LOCAL_BASE_URL` (por defecto `http://127.0.0.1:11434/api`).
3. No necesitas una clave para el servidor local.

El reporte PDP incluye `ai.providers`, donde se puede ver qué proveedor respondió, cuál fue omitido, cuál agotó su cuota y qué proveedor actuó como respaldo. Las respuestas directas de `/api/ai/generate` también incluyen `usage` y `rate_limits` cuando el proveedor los informa.

## Tests

```powershell
python -m pytest backend/tests -q
```

Los tests usan archivos SQLite temporales y no modifican la base de datos local.

## Estructura importante

```text
frontend/                 Interfaz Electron y renderer.
frontend/src/renderer/bot-module.js Constructor manual y controles del Bot de formularios.
backend/app/automations/generic_bot/runner.py Ejecutor de pasos web con Playwright.
storage/browser_profiles/chrome-qa Perfil persistente usado por Google Chrome para QA.
backend/app/automations/generic_bot/runner.py Ejecutor headless de scripts manuales con Playwright.
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

El Bot de formularios permite definir manualmente cada acción, selector y valor. El ejecutor corre en segundo plano, registra cada resultado y guarda evidencias, sin abrir un navegador para grabar la interacción.

## Crear un script manual

1. Escribe el nombre y la URL inicial.
2. Elige una acción, completa su selector/objetivo y su valor cuando aplique.
3. Pulsa **Agregar paso** y repite el proceso en el orden exacto de ejecución.
4. Reordena o elimina pasos, valida el script y guárdalo.
5. Pulsa **Ejecutar en segundo plano**. Playwright ejecutará el flujo sin mostrar el navegador y conservará las capturas de evidencia.

Usa selectores `css=`, `label=`, `text=`, `testid=` o `role=button[name=Enviar]`. Evita guardar tokens o datos sensibles en la configuración.
