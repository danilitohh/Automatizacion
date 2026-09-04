# Mapa de módulos

## Bot de nuevos productos
- Backend: `backend/app/modules/bot_nuevos_productos/`
- Frontend: `frontend/src/modules/bot_nuevos_productos/`

## Bot Leads Deploy
- Backend: `backend/app/modules/bot_leads_deploy/`
- Frontend: `frontend/src/modules/bot_leads_deploy/`

## Generic Bot
- Backend: `backend/app/modules/generic_bot/`
- Frontend/API: `frontend/src/modules/generic_bot/`

## Weekly Auto
- Backend: `backend/app/modules/weekly_auto/`
- Frontend: `frontend/src/modules/weekly_auto/`

## PDP Validation
- Backend: `backend/app/modules/pdp_validation/`
- Frontend: `frontend/src/modules/pdp_validation/`

## Plataforma compartida
Cambios aquí sí pueden afectar varios módulos:
- `backend/app/config/`
- `backend/app/database/`
- `backend/app/schemas/` (solo contratos de plataforma/compatibilidad)
- `backend/app/services/ai_service.py`
- `backend/app/services/logging_service.py`
- `backend/app/services/dashboard_service.py`
- `frontend/src/renderer/app.js`
- `frontend/src/renderer/styles.css`
- `frontend/src/services/api.js`

Regla: para cambiar un bot, empieza siempre por su carpeta de módulo.
