try:  # Celery est optionnel en développement
    from .celery import app as celery_app

    __all__ = ("celery_app",)
except ImportError:  # pragma: no cover
    pass
