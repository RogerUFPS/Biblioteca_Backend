from django.core.management.base import BaseCommand

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    Institution,
    KnowledgeArea,
    Language,
    MaterialType,
)


class Command(BaseCommand):
    help = "Carga datos base del catálogo de forma idempotente."

    def handle(self, *_args, **_options):
        user = User.all_objects.get(code=0)
        records = (
            (Language, {"abbreviation": "es", "name": "Español"}),
            (Language, {"abbreviation": "en", "name": "Inglés"}),
            (Country, {"name": "Colombia", "abbreviation": "CO", "emoji_flag": "🇨🇴"}),
            (Country, {"name": "México", "abbreviation": "MX", "emoji_flag": "🇲🇽"}),
            (MaterialType, {"name": "Artículo"}),
            (MaterialType, {"name": "Libro"}),
            (Institution, {"name": "Universidad Francisco de Paula Santander"}),
            (Editorial, {"name": "Editorial Académica"}),
            (KnowledgeArea, {"name": "Ciencias de la computación"}),
            (KnowledgeArea, {"name": "Ingeniería"}),
            (AcademicProgram, {"name": "Ingeniería de Sistemas"}),
        )

        created_count = 0
        for model, values in records:
            instance, created = model.all_objects.get_or_create(
                **values,
                defaults={"created_by": user},
            )
            if created:
                created_count += 1
            elif instance.deleted_at is not None:
                instance.restore()

        self.stdout.write(
            self.style.SUCCESS(f"Catálogo cargado. Registros creados: {created_count}.")
        )
