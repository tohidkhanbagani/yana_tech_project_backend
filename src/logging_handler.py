import logging

class DBAuditLogHandler(logging.Handler):
    """
    Deprecated handler. Database backend logging has been disabled
    to prevent memory overhead and database bloat.
    """
    def __init__(self, level=logging.WARNING):
        super().__init__(level)

    def emit(self, record):
        # Database backend logging disabled
        pass
