"""Runner exclusivo de Bot Leads Deploy.

Este adaptador conserva el import usado por la API y ejecuta la implementación
propia de Leads Deploy. La verificación CRM usa el destino indicado por el Excel
como prioridad y consulta el otro sistema como respaldo, sin reenviar UTEL.
"""

from ...modules.bot_leads_deploy.dual_crm_runner import LeadsDeployDualCrmRunner


class LeadsDeployRunner(LeadsDeployDualCrmRunner):
    """Punto de entrada aislado para el flujo Leads Deploy."""

    pass
