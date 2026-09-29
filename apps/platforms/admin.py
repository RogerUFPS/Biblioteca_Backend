from django.contrib import admin

from . import models

for model in [
    models.Platform,
    models.ValidSintaxis,
    models.LinkCheckLog,
    models.SharedPlatformSupport,
    models.SharedPlatformLanguage,
    models.SharedPlatformCountry,
    models.SharedPlatformKnowledgeArea,
    models.SharedPlatformMaterialType,
    models.SharedPlatformAcademicProgram,
]:
    admin.site.register(model)
