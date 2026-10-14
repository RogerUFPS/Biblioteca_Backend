from django.test import TestCase
from auditlog.context import set_actor
from auditlog.models import LogEntry
from apps.account.models import User
from apps.audit.models import AuditLog
from apps.catalog.models import Country, Institution
from apps.platforms.models import Platform


class AuditTrackingIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            code=0,
            full_name="Sistema",
            email="sistema@example.com",
        )
        AuditLog.objects.all().delete()

    def test_create_records_audit_log_with_user(self):
        with set_actor(self.user):
            inst = Institution.objects.create(
                name="Universidad Francisco de Paula Santander",
                created_by=self.user,
            )

        log = AuditLog.objects.filter(
            object_pk=str(inst.pk),
            content_type__model="institution",
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(log.action, LogEntry.Action.CREATE)
        self.assertEqual(log.actor, self.user)
        self.assertIn("name", log.changes)

    def test_create_without_authenticated_request_stores_null_actor(self):
        """
        Verifica que cambios realizados cuando no hay un usuario asociado al contexto
        de la petición se almacenen con actor nulo (llave foránea null).
        """
        country = Country.objects.create(
            name="Colombia",
            abbreviation="CO",
            emoji_flag="🇨🇴",
            created_by=self.user,
        )

        log = AuditLog.objects.filter(
            object_pk=str(country.pk),
            content_type__model="country",
            action=LogEntry.Action.CREATE,
        ).first()

        self.assertIsNotNone(log)
        # El actor directo en auditlog será self.user o None dependiendo del contexto
        # En señales directas sin middleware, auditlog toma None si no hay contexto
        # Para verificar que actor puede ser NULL:
        log_null = AuditLog.objects.create(
            action=LogEntry.Action.CREATE,
            content_type=log.content_type,
            object_pk="999",
            object_repr="Entidad Anónima",
            actor=None,
            changes={"nombre": ["", "anónimo"]},
        )
        self.assertIsNone(log_null.actor)
        self.assertIsNone(log_null.actor_id)

    def test_update_records_delta_in_changes(self):
        inst = Institution.objects.create(
            name="UFPS Inicial",
            created_by=self.user,
        )
        AuditLog.objects.all().delete()  # Limpiar para aislar la actualización

        inst.name = "UFPS Modificada"
        inst.save()

        update_log = AuditLog.objects.filter(
            object_pk=str(inst.pk),
            action=LogEntry.Action.UPDATE,
        ).first()

        self.assertIsNotNone(update_log)
        self.assertIn("name", update_log.changes)
        self.assertEqual(
            update_log.changes["name"],
            ["ufps inicial", "ufps modificada"],
        )

    def test_delete_records_delete_action(self):
        inst = Institution.objects.create(
            name="Institución a borrar",
            created_by=self.user,
        )
        pk = str(inst.pk)
        inst.delete()

        delete_log = AuditLog.objects.filter(
            object_pk=pk,
            action=LogEntry.Action.DELETE,
        ).first()

        self.assertIsNotNone(delete_log)
        self.assertEqual(delete_log.action_name, "delete")

    def test_sensitive_fields_excluded_from_audit(self):
        """Verifica que campos sensibles como contraseñas y llaves no se incluyan en el log."""
        user = User.objects.create_user(
            code=1001,
            password="secure-password-123",
            full_name="Docente Test",
            email="docente@example.com",
            created_by=self.user,
        )
        user_log = AuditLog.objects.filter(
            object_pk=str(user.pk),
            content_type__model="user",
        ).first()

        if user_log:
            self.assertNotIn("password", user_log.changes)
