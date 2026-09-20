from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import SoftDeleteMixin, SoftDeleteQuerySet


class UserManager(BaseUserManager):
    """Manager por defecto: solo devuelve usuarios activos."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def create_user(self, code, password=None, created_by=None, **extra_fields):
        if code is None:
            raise ValueError("El usuario debe tener un código.")

        user = self.model(code=code, created_by=created_by, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, code, password=None, created_by=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(
            code,
            password=password,
            created_by=created_by,
            **extra_fields,
        )


class User(SoftDeleteMixin, AbstractBaseUser):
    """Administrador del sistema identificado por su código."""

    code = models.IntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users_updated",
    )
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users_deleted",
    )

    objects = UserManager()
    all_objects = models.Manager()

    USERNAME_FIELD = "code"
    REQUIRED_FIELDS = ["full_name", "email"]

    def __str__(self):
        return f"{self.code} - {self.full_name}"

    def _validate_creator(self):
        if self.pk is None and self.created_by_id is None and User.all_objects.exists():
            raise ValidationError(
                {"created_by": "Solo el primer usuario puede no tener creador."}
            )

    def clean(self):
        super().clean()
        self._validate_creator()

    def save(self, *args, **kwargs):
        if self.pk is None:
            self._validate_creator()
        return super().save(*args, **kwargs)

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser
