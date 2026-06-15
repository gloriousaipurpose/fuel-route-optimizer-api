from django.apps import AppConfig


class FuelPlannerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fuel_planner'

    def ready(self):
        # Prevent initialization during migration/management commands if necessary,
        # but loading from CSV is fast enough that it is fine to run on startup.
        try:
            from .services.fuel_data import initialize_stations
            initialize_stations()
        except Exception:
            # Avoid crashing if databases/directories aren't fully set up yet (e.g. during initialization scripts)
            pass
