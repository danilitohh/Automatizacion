# Instalación y tecnologías

La interfaz usa HTML, CSS y JavaScript con módulos ES nativos; no necesita React ni un compilador frontend. Consume la API mediante fetch. FastAPI sirve la interfaz en modo web. Electron 36 es la envoltura de escritorio y Node.js ejecuta los lanzadores.

El backend utiliza Python, FastAPI, Uvicorn, Pydantic Settings, HTTPX, cloudscraper y python-multipart. SQLite viene incluido con Python y no necesita un servidor separado. Playwright controla los navegadores. openpyxl procesa Excel, python-docx Word, pypdf PDF y phonenumbers valida teléfonos. pytest ejecuta pruebas. Las versiones admitidas están en backend/requirements.txt y package.json; npm ci respeta package-lock.json.

## Nuevo equipo Windows

1. Copiar o clonar el proyecto sin .venv, node_modules, .env ni perfiles privados de storage.
2. Abrir Iniciar.cmd. No necesita Node ni Python para mostrar el asistente.
3. Leer la lista de instalaciones y escribir SI para autorizarlas. Cancelar no instala nada y no inicia la app.
4. El asistente instala los runtimes faltantes mediante winget, crea .venv, instala los requisitos Python, Electron y Chromium, y comprueba dependencias. Puede aparecer el aviso de permisos de Windows. Si winget falta, muestra instrucciones y se detiene.
5. Configurar las credenciales propias en .env e iniciar sesión en los CRM cuando corresponda. Las claves, sesiones y permisos externos no se pueden crear instalando librerías.
6. Cuando la consola indique que el servidor está listo, abrir http://127.0.0.1:8000.

Cada arranque con Iniciar.cmd, npm run web o npm start revisa la preparación. Solicita autorización si falta la preparación o cambian los manifiestos, la carpeta o el equipo. No reinstala cuando la comprobación pasa. Ejecutar Uvicorn directamente omite este asistente.

Diagnóstico sin instalaciones: powershell -NoProfile -File scripts/setup-windows.ps1 -CheckOnly. Código 0: listo; 2: preparación pendiente; 1: error.

Ollama local es opcional: requiere instalar Ollama y descargar un modelo adecuado al hardware. Los proveedores remotos necesitan claves y conexión. El asistente no descarga modelos grandes ni configura cuentas automáticamente. No instala Brave ni navegadores adicionales opcionales.

## Otros sistemas y dispositivos

El asistente incluido es para Windows con winget. No se ha certificado la automatización completa en macOS o Linux: existen rutas y funciones específicas de Windows. Estos sistemas requieren preparar Python, Node y los navegadores manualmente y validar cada módulo; en Linux Playwright puede necesitar bibliotecas del sistema.

Un móvil o una tableta puede actuar como cliente de una instalación web accesible, pero no ejecutar este instalador ni los bots locales. El navegador no puede instalar Python, Electron o programas del sistema. Publicar la app para acceso remoto requiere configurar alojamiento y autenticación antes de exponer el backend; este cambio no la publica ni cambia sus permisos de red.

## Alcance de verificación

El diagnóstico y la sintaxis se verifican sin instalar paquetes en el equipo de desarrollo. La instalación limpia de runtimes requiere una prueba adicional en un Windows nuevo o una máquina virtual; no se garantiza compatibilidad universal por instalar dependencias.
