# Mapa de módulos

Esta rama separa progresivamente cada automatización para que los cambios específicos se hagan dentro de su propia carpeta.

## Bot de nuevos productos
Backend: `backend/app/modules/bot_nuevos_productos/`
Frontend: `frontend/src/modules/bot_nuevos_productos/`

## Bot Leads Deploy
Backend: `backend/app/modules/bot_leads_deploy/`
Frontend: `frontend/src/modules/bot_leads_deploy/`

## Generic Bot
Backend: `backend/app/modules/generic_bot/`

## Weekly Auto
Backend: `backend/app/modules/weekly_auto/`
Frontend: `frontend/src/modules/weekly_auto/`

## PDP Validation
Backend: `backend/app/modules/pdp_validation/`
Frontend: `frontend/src/modules/pdp_validation/`

## Archivos compartidos
`backend/app/config`, `backend/app/database`, `backend/app/schemas`, logging, IA, `frontend/src/renderer/app.js` y los estilos generales siguen siendo infraestructura común.

Regla de trabajo: para cambiar un bot, empieza por su carpeta de módulo. No edites archivos de otro módulo.
