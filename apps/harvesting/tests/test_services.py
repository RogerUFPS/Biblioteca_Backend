from unittest.mock import MagicMock
from django.test import TestCase
import httpx

from apps.account.models import User
from apps.harvesting.models import Harvest, Schedule
from apps.harvesting.services import OpenAlexHarvester
from apps.journal.models import Journal, SharedJournalPlatform
from apps.platforms.models import Platform


class HarvestingServicesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            code=0,
            full_name="Sistema",
            email="sistema@test.local",
        )
        cls.platform = Platform.objects.create(
            name="OpenAlex Services Test",
            base_api_url="https://api.openalex.org",
            created_by=cls.user,
        )

    def test_openalex_harvester_creates_and_deduplicates_journals(self):
        # Simular respuestas de OpenAlex
        mock_response_1 = MagicMock(spec=httpx.Response)
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {
            "meta": {"next_cursor": "cursor_page_2"},
            "results": [
                {
                    "id": "https://openalex.org/S1",
                    "display_name": "Revista Uno",
                    "issn_l": "1111-1111",
                    "issn": ["1111-1111"],
                    "host_organization_name": "Editorial Uno",
                    "is_oa": True,
                },
                {
                    "id": "https://openalex.org/S2",
                    "display_name": "Revista Dos",
                    "issn_l": "2222-2222",
                    "issn": ["2222-2222"],
                    "is_oa": False,
                },
            ],
        }

        mock_response_2 = MagicMock(spec=httpx.Response)
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "meta": {"next_cursor": None},
            "results": [],
        }

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [mock_response_1, mock_response_2]

        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )

        harvester = OpenAlexHarvester(
            harvest=harvest,
            client=mock_client,
            user=self.user,
        )
        harvester.harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.COMPLETED)
        self.assertEqual(harvest.records_added, 2)
        self.assertEqual(harvest.records_updated, 0)
        self.assertEqual(harvest.api_cursor, "cursor_page_2")

        # Verificar que se crearon los Journals y los vínculos SharedJournalPlatform
        j1 = Journal.objects.get(issn="1111-1111")
        self.assertEqual(j1.title, "Revista Uno")
        self.assertTrue(SharedJournalPlatform.objects.filter(journal=j1, platform=self.platform).exists())

        # Probar deduplicación: Segunda cosecha con los mismos datos
        mock_response_dup = MagicMock(spec=httpx.Response)
        mock_response_dup.status_code = 200
        mock_response_dup.json.return_value = {
            "meta": {"next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/S1",
                    "display_name": "Revista Uno Actualizada",
                    "issn_l": "1111-1111",
                    "is_oa": True,
                }
            ],
        }
        mock_client_dup = MagicMock(spec=httpx.Client)
        mock_client_dup.get.return_value = mock_response_dup

        harvest_2 = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )

        harvester_2 = OpenAlexHarvester(
            harvest=harvest_2,
            client=mock_client_dup,
            user=self.user,
        )
        harvester_2.harvest_records()

        harvest_2.refresh_from_db()
        self.assertEqual(harvest_2.records_added, 0)
        self.assertEqual(harvest_2.records_updated, 1)

        # No se duplicó el registro en la BD
        self.assertEqual(Journal.objects.filter(issn="1111-1111").count(), 1)
        j1.refresh_from_db()
        self.assertEqual(j1.title, "Revista Uno Actualizada")

    def test_harvest_updates_schedule_timing_automatically(self):
        schedule = Schedule.objects.create(
            platform=self.platform,
            frequency=Schedule.Frequency.DAILY,
            max_quantity=10,
            created_by=self.user,
        )
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meta": {"next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/S1",
                    "display_name": "Revista Timing",
                    "issn_l": "3333-3333",
                    "issn": ["3333-3333"],
                }
            ],
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        harvest = Harvest.objects.create(
            platform=self.platform,
            schedule=schedule,
            max_quantity=10,
            created_by=self.user,
        )
        OpenAlexHarvester(
            harvest=harvest,
            client=mock_client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        schedule.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.COMPLETED)
        self.assertIsNotNone(harvest.started_at)
        self.assertIsNotNone(harvest.finished_at)
        self.assertEqual(schedule.start_date, harvest.started_at)
        self.assertEqual(schedule.finish_date, harvest.finished_at)
        self.assertEqual(schedule.duration, harvest.finished_at - harvest.started_at)
        self.assertGreaterEqual(schedule.duration.total_seconds(), 0)
