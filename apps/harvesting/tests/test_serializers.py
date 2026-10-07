from django.test import TestCase
from django.utils import timezone

from apps.account.models import User
from apps.harvesting.models import Harvest, Schedule
from apps.harvesting.serializers import HarvestSerializer, ScheduleSerializer
from apps.platforms.models import Platform


class HarvestingSerializersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )
        cls.platform = Platform.objects.create(
            name="OpenAlex",
            base_api_url="https://api.openalex.org",
            created_by=cls.user,
        )

    def test_schedule_serializer_validation_success(self):
        data = {
            "platform": self.platform.pk,
            "frequency": "daily",
            "max_quantity": 500,
        }
        serializer = ScheduleSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        schedule = serializer.save(created_by=self.user)
        self.assertEqual(schedule.platform, self.platform)
        self.assertIsNone(schedule.start_date)
        self.assertIsNone(schedule.finish_date)
        self.assertIsNone(schedule.duration)

    def test_schedule_serializer_ignores_timing_fields_from_user(self):
        now = timezone.now()
        data = {
            "platform": self.platform.pk,
            "frequency": "daily",
            "stop_after_minutes": 30,
            "start_date": now.isoformat(),
            "finish_date": now.isoformat(),
            "duration": "02:00:00",
            "is_active": False,
        }
        serializer = ScheduleSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        schedule = serializer.save(created_by=self.user)
        self.assertIsNone(schedule.start_date)
        self.assertIsNone(schedule.finish_date)
        self.assertIsNone(schedule.duration)

    def test_schedule_serializer_requires_a_limit(self):
        data = {
            "platform": self.platform.pk,
            "frequency": "weekly",
        }
        serializer = ScheduleSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_harvest_serializer_requires_limits(self):
        data = {
            "platform": self.platform.pk,
        }
        serializer = HarvestSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_harvest_serializer_requires_platform_or_schedule(self):
        data = {
            "max_quantity": 100,
        }
        serializer = HarvestSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("platform", serializer.errors)

    def test_harvest_serializer_inherits_platform_and_limits_from_schedule(self):
        schedule = Schedule.objects.create(
            platform=self.platform,
            frequency=Schedule.Frequency.WEEKLY,
            max_quantity=80,
            stop_after_minutes=15,
            created_by=self.user,
        )
        serializer = HarvestSerializer(data={"schedule": schedule.pk})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        harvest = serializer.save(created_by=self.user)
        self.assertEqual(harvest.platform, self.platform)
        self.assertEqual(harvest.max_quantity, 80)
        self.assertEqual(harvest.stop_after_minutes, 15)

    def test_harvest_serializer_auto_cursor_recovery(self):
        Harvest.objects.create(
            platform=self.platform,
            api_cursor="cursor_test_token_123",
            max_quantity=50,
            state=Harvest.State.COMPLETED,
            created_by=self.user,
        )

        data = {
            "platform": self.platform.pk,
            "max_quantity": 100,
        }
        serializer = HarvestSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        harvest = serializer.save(created_by=self.user)
        self.assertEqual(harvest.api_cursor, "cursor_test_token_123")

    def test_harvest_serializer_rejects_when_active_exists(self):
        Harvest.objects.create(
            platform=self.platform,
            max_quantity=50,
            state=Harvest.State.RUNNING,
            created_by=self.user,
        )

        data = {
            "platform": self.platform.pk,
            "max_quantity": 100,
        }
        serializer = HarvestSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("platform", serializer.errors)

    def test_harvest_serializer_ignores_user_provided_runtime_fields(self):
        Harvest.objects.create(
            platform=self.platform,
            api_cursor="cursor_autentico_anterior",
            max_quantity=50,
            state=Harvest.State.COMPLETED,
            created_by=self.user,
        )

        data = {
            "platform": self.platform.pk,
            "max_quantity": 100,
            "api_cursor": "cursor_arbitrario_del_usuario",
            "state": "completed",
            "records_added": 999,
            "started_at": timezone.now().isoformat(),
            "finished_at": timezone.now().isoformat(),
            "error_message": "no debe persistir",
        }
        serializer = HarvestSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        harvest = serializer.save(created_by=self.user)
        self.assertEqual(harvest.api_cursor, "cursor_autentico_anterior")
        self.assertEqual(harvest.state, Harvest.State.PENDING)
        self.assertEqual(harvest.records_added, 0)
        self.assertIsNone(harvest.started_at)
        self.assertIsNone(harvest.finished_at)
        self.assertIsNone(harvest.error_message)
