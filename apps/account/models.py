from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, code, password=None, created_by=None, **extra_fields):
        if code is None:
            raise ValueError("El usuario debe tener un codigo.")

        user = self.model(code=code, created_by=created_by, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(code, password=password, **extra_fields)


class User(AbstractBaseUser):
    """Usuario del sistema identificado por su codigo."""

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
    delete_explanation = models.CharField(max_length=500, null=True, blank=True)
    deleted_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users_deleted",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "code"
    REQUIRED_FIELDS = ["full_name", "email"]

    def __str__(self):
        return f"{self.code} - {self.full_name}"

    def clean(self):
        super().clean()
        if self.pk is None and self.created_by_id is None and type(self).objects.exists():
            raise ValidationError(
                {"created_by": "Solo el primer usuario puede no tener creador."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def has_perm(self, _perm, _obj=None):
        return self.is_superuser

    def has_module_perms(self, _app_label):
        return self.is_superuser

    @property
    def is_deleted(self):
        return self.deleted_at is not None
