"""Runner exclusivo de Bot Leads Deploy.

Este adaptador conserva el import usado por la API y ejecuta la implementación
propia de Leads Deploy, sin heredar el runner general de otros bots.
"""

from ...modules.bot_leads_deploy.runner import UtelInconcertRunner


class LeadsDeployRunner(UtelInconcertRunner):
    """Punto de extensión aislado para el flujo Leads Deploy."""

    pass
