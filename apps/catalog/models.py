from django.db import models

from apps.core.models import AuditableModel


class Institution(AuditableModel):
    """Institucion encargada de administrar una o mas plataformas."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Language(AuditableModel):
    """Idioma disponible."""

    abbreviation = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.abbreviation} - {self.name}"


class Country(AuditableModel):
    """Pais disponible."""

    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)
    emoji_flag = models.CharField(max_length=16)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return f"{self.emoji_flag} {self.name}"


class MaterialType(AuditableModel):
    """Tipo de material que puede ofrecer una plataforma."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Editorial(AuditableModel):
    """Organizacion encargada de publicar una revista."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class KnowledgeArea(AuditableModel):
    """Area del conocimiento."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AcademicProgram(AuditableModel):
    """Programa academico."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SharedAcademicProgramKnowledgeArea(AuditableModel):
    """Relacion explicita entre programas y areas del conocimiento."""

    knowledge_area = models.ForeignKey(
        KnowledgeArea,
        on_delete=models.PROTECT,
        related_name="program_links",
    )
    academic_program = models.ForeignKey(
        AcademicProgram,
        on_delete=models.PROTECT,
        related_name="knowledge_area_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_area", "academic_program"],
                name="unique_program_knowledge_area",
            )
        ]

    def __str__(self):
        return f"{self.academic_program} <-> {self.knowledge_area}"
