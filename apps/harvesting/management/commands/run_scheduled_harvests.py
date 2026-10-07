from django.core.management.base import BaseCommand
from apps.harvesting.services import run_scheduled_harvests


class Command(BaseCommand):
    help = "Evalúa las programaciones no eliminadas (Schedule) y ejecuta cosechas según su frecuencia."

    def handle(self, *args, **options):
        self.stdout.write("Evaluando programaciones de cosecha...")
        harvests = run_scheduled_harvests()
        if not harvests:
            self.stdout.write(self.style.SUCCESS("No hay programaciones pendientes de ejecución en este momento."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Se ejecutaron {len(harvests)} cosechas programadas exitosamente: {[h.pk for h in harvests]}."
                )
            )
