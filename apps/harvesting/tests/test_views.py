from rest_framework import status
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.harvesting.models import Harvest, Schedule
from apps.platforms.models import Platform


class HarvestingViewsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )
        cls.platform = Platform.objects.create(
            name="OpenAlex Test",
            base_api_url="https://api.openalex.org",
            created_by=cls.user,
        )

    def test_schedule_crud_operations(self):
        payload = {
            "platform": self.platform.pk,
            "frequency": "weekly",
            "max_quantity": 250,
        }
        res_create = self.client.post("/api/harvesting/schedules/", payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        schedule_id = res_create.data["id"]
        self.assertIsNone(res_create.data["start_date"])
        self.assertIsNone(res_create.data["finish_date"])
        self.assertIsNone(res_create.data["duration"])
        self.assertNotIn("is_active", res_create.data)

        res_get = self.client.get(f"/api/harvesting/schedules/{schedule_id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data["frequency"], "weekly")

        res_patch = self.client.patch(
            f"/api/harvesting/schedules/{schedule_id}/",
            {"frequency": "monthly"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["frequency"], "monthly")

        res_delete = self.client.delete(
            f"/api/harvesting/schedules/{schedule_id}/",
            {"delete_explanation": "Prueba de borrado"},
            format="json",
        )
        self.assertIn(res_delete.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_schedule_create_does_not_accept_timing_from_user(self):
        payload = {
            "platform": self.platform.pk,
            "frequency": "daily",
            "stop_after_minutes": 20,
            "start_date": "2026-10-15T02:00:00Z",
            "finish_date": "2026-12-31T23:59:59Z",
            "duration": "02:00:00",
            "is_active": False,
        }
        response = self.client.post("/api/harvesting/schedules/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["start_date"])
        self.assertIsNone(response.data["finish_date"])
        self.assertIsNone(response.data["duration"])
        self.assertNotIn("is_active", response.data)

    def test_harvest_inalterability_blocks_put_patch_delete(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            created_by=self.user,
        )

        res_put = self.client.put(
            f"/api/harvesting/harvests/{harvest.pk}/",
            {"max_quantity": 200},
            format="json",
        )
        self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_patch = self.client.patch(
            f"/api/harvesting/harvests/{harvest.pk}/",
            {"records_added": 999},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_delete = self.client.delete(f"/api/harvesting/harvests/{harvest.pk}/")
        self.assertEqual(res_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_harvest_cancel_and_retry_actions(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            state=Harvest.State.PENDING,
            created_by=self.user,
        )

        res_cancel = self.client.post(f"/api/harvesting/harvests/{harvest.pk}/cancel/")
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data["state"], "cancelled")

        res_retry = self.client.post(f"/api/harvesting/harvests/{harvest.pk}/retry/")
        self.assertEqual(res_retry.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(res_retry.data["id"], harvest.pk)
        self.assertEqual(res_retry.data["state"], "pending")
