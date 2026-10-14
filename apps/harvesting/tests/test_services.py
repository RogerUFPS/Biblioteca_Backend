from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.utils import timezone
import httpx

from apps.account.models import User
from apps.catalog.models import Country
from apps.harvesting.models import Harvest, Schedule, ScheduleEvent
from apps.harvesting.services import (
    OpenAlexHarvester,
    _next_occurrence,
    get_harvester_for_platform,
    run_scheduled_harvests,
)
from apps.journal.models import Journal, SharedJournalPlatform
from apps.platforms.models import LinkCheckLog, Platform


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
            status=Platform.Status.PUBLICADO,
            base_api_url="https://api.openalex.org",
            is_harvestable=True,
            created_by=cls.user,
        )

    def test_default_openalex_client_does_not_advertise_email(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )
        client = OpenAlexHarvester(harvest=harvest, user=self.user)._get_client()
        try:
            self.assertEqual(
                client.headers["User-Agent"],
                "UFPS-Harvester/1.0",
            )
            self.assertNotIn("mailto:", client.headers["User-Agent"])
            self.assertEqual(client.headers["Accept"], "application/json")
        finally:
            client.close()

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
                    "homepage_url": "https://8.8.8.8/revista-uno",
                    "host_organization_name": "Editorial Uno",
                    "is_oa": True,
                },
                {
                    "id": "https://openalex.org/S2",
                    "display_name": "Revista Dos",
                    "issn_l": "2222-2222",
                    "issn": ["2222-2222"],
                    "homepage_url": "https://8.8.8.8/revista-dos",
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
        country = Country.objects.create(
            name="United States",
            abbreviation="US",
            emoji_flag="🇺🇸",
            created_by=self.user,
        )
        mock_response_1.json.return_value["results"][0].update({
            "country_code": "US",
            "image_thumbnail_url": "https://example.test/journal.png",
            "is_active": True,
            "apc_usd": 1400,
            "license": "CC-BY",
        })

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
        self.assertEqual(mock_client.get.call_args_list[0].kwargs["params"]["cursor"], "*")

        # Verificar que se crearon los Journals y los vínculos SharedJournalPlatform
        j1 = Journal.objects.get(issn="1111-1111")
        self.assertEqual(j1.title, "Revista Uno")
        self.assertEqual(j1.url_image, "https://example.test/journal.png")
        self.assertFalse(j1.active)
        self.assertTrue(j1.has_apc)
        journal_platform = SharedJournalPlatform.objects.get(
            journal=j1,
            platform=self.platform,
        )
        self.assertEqual(
            LinkCheckLog.objects.get(journal_platform=journal_platform).url,
            "https://8.8.8.8/revista-uno",
        )
        self.assertFalse(j1.license_links.exists())
        self.assertTrue(j1.country_links.filter(country=country).exists())
        self.assertTrue(journal_platform)

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
                    "homepage_url": "https://8.8.8.8/revista-uno-actualizada",
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
        self.assertEqual(harvest_2.api_cursor, "cursor_page_2")

        # No se duplicó el registro en la BD
        self.assertEqual(Journal.objects.filter(issn="1111-1111").count(), 1)
        j1.refresh_from_db()
        self.assertEqual(j1.title, "Revista Uno Actualizada")
        self.assertFalse(j1.active)
        self.assertTrue(j1.has_apc)

    def test_harvest_records_runtime_timestamps(self):
        scheduled_for = timezone.now() - timedelta(minutes=1)
        schedule = Schedule.objects.create(
            frequency=Schedule.Frequency.DAILY,
            max_quantity=10,
            start_date=scheduled_for,
            created_by=self.user,
        )
        schedule.platforms.add(self.platform)
        event = ScheduleEvent.objects.create(
            schedule=schedule,
            scheduled_for=scheduled_for,
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
                    "homepage_url": "https://8.8.8.8/revista-timing",
                }
            ],
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        harvest = Harvest.objects.create(
            platform=self.platform,
            schedule=schedule,
            event=event,
            max_quantity=10,
            created_by=self.user,
        )
        OpenAlexHarvester(
            harvest=harvest,
            client=mock_client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.COMPLETED)
        self.assertIsNotNone(harvest.started_at)
        self.assertIsNotNone(harvest.finished_at)

    @patch("apps.harvesting.services.execute_harvest")
    def test_scheduled_event_creates_one_harvest_per_platform(self, execute_harvest):
        def complete_harvest(harvest_id):
            Harvest.objects.filter(pk=harvest_id).update(
                state=Harvest.State.COMPLETED,
                finished_at=timezone.now(),
            )

        execute_harvest.side_effect = complete_harvest
        second_platform = Platform.objects.create(
            name="Second Harvest Platform",
            status=Platform.Status.PUBLICADO,
            base_api_url="https://api.openalex.org",
            is_harvestable=True,
            created_by=self.user,
        )
        now = timezone.now()
        schedule = Schedule.objects.create(
            frequency=Schedule.Frequency.DAILY,
            max_quantity=10,
            start_date=now - timedelta(days=2),
            created_by=self.user,
        )
        schedule.platforms.add(self.platform, second_platform)

        first_harvests = run_scheduled_harvests(now=now)
        self.assertEqual(len(first_harvests), 2)
        event = ScheduleEvent.objects.get(schedule=schedule)
        self.assertEqual(event.state, ScheduleEvent.State.COMPLETED)
        self.assertEqual(event.harvests.count(), 2)
        self.assertEqual(execute_harvest.call_count, 2)

        next_harvests = run_scheduled_harvests(now=now + timedelta(days=1))
        self.assertEqual(len(next_harvests), 2)
        self.assertEqual(schedule.events.count(), 2)

    def test_scheduled_harvest_fails_if_platform_was_disabled(self):
        self.platform.is_harvestable = False
        self.platform.save(update_fields=["is_harvestable"])
        now = timezone.now()
        schedule = Schedule.objects.create(
            frequency=Schedule.Frequency.ONCE,
            max_quantity=10,
            start_date=now - timedelta(minutes=1),
            created_by=self.user,
        )
        schedule.platforms.add(self.platform)

        harvests = run_scheduled_harvests(now=now)

        self.assertEqual(len(harvests), 1)
        self.assertEqual(harvests[0].state, Harvest.State.FAILED)
        self.assertIn("no está habilitada para cosecha", harvests[0].error_message)
        self.assertEqual(schedule.events.get().state, ScheduleEvent.State.FAILED)

    def test_non_harvestable_platform_has_no_harvester(self):
        self.platform.is_harvestable = False
        self.platform.save(update_fields=["is_harvestable"])
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )

        with self.assertRaisesMessage(ValueError, "is_harvestable=false"):
            get_harvester_for_platform(harvest)

        with self.assertRaisesMessage(ValueError, "is_harvestable=false"):
            OpenAlexHarvester(harvest, user=self.user).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.PENDING)

    def test_max_quantity_counts_failed_records_too(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {
            "meta": {"next_cursor": "cursor_page_2"},
            "results": [
                {"display_name": "No ISSN"},
                {
                    "display_name": "Should not be processed",
                    "issn_l": "4444-4444",
                },
            ],
        }
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = response
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=1,
            created_by=self.user,
        )

        OpenAlexHarvester(
            harvest=harvest,
            client=client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.records_failed, 1)
        self.assertEqual(harvest.records_added, 0)
        self.assertEqual(harvest.api_cursor, "*")
        self.assertEqual(client.get.call_count, 1)

    def test_openalex_source_without_homepage_url_is_counted_as_failed(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {
            "meta": {"next_cursor": None},
            "results": [
                {
                    "display_name": "Journal without homepage",
                    "issn_l": "7777-7777",
                }
            ],
        }
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = response
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )

        OpenAlexHarvester(
            harvest=harvest,
            client=client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.COMPLETED)
        self.assertEqual(harvest.records_added, 0)
        self.assertEqual(harvest.records_failed, 1)
        self.assertFalse(Journal.objects.filter(issn="7777-7777").exists())

    def test_pause_finishes_current_page_and_resume_uses_saved_cursor(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {
            "meta": {"next_cursor": "resume-cursor"},
            "results": [
                {
                    "display_name": "Pause-safe journal",
                    "issn_l": "5555-5555",
                    "homepage_url": "https://8.8.8.8/pause-safe",
                }
            ],
        }
        client = MagicMock(spec=httpx.Client)

        def pause_during_request(*args, **kwargs):
            Harvest.objects.filter(pk=harvest.pk).update(
                state=Harvest.State.PAUSING,
            )
            return response

        client.get.side_effect = pause_during_request
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )

        OpenAlexHarvester(
            harvest=harvest,
            client=client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.PAUSED)
        self.assertEqual(harvest.api_cursor, "resume-cursor")
        self.assertEqual(harvest.records_added, 1)
        self.assertIsNone(harvest.finished_at)

        Harvest.objects.filter(pk=harvest.pk).update(state=Harvest.State.PENDING)
        resumed_response = MagicMock(spec=httpx.Response)
        resumed_response.status_code = 200
        resumed_response.json.return_value = {
            "meta": {"next_cursor": None},
            "results": [],
        }
        resumed_client = MagicMock(spec=httpx.Client)
        resumed_client.get.return_value = resumed_response
        OpenAlexHarvester(
            harvest=Harvest.objects.get(pk=harvest.pk),
            client=resumed_client,
            user=self.user,
        ).harvest_records()

        self.assertEqual(
            resumed_client.get.call_args.kwargs["params"]["cursor"],
            "resume-cursor",
        )

    def test_resumed_harvest_keeps_elapsed_time_limit(self):
        client = MagicMock(spec=httpx.Client)
        harvest = Harvest.objects.create(
            platform=self.platform,
            stop_after_minutes=1,
            elapsed_seconds=60,
            created_by=self.user,
        )
        OpenAlexHarvester(
            harvest=harvest,
            client=client,
            user=self.user,
        ).harvest_records()

        harvest.refresh_from_db()
        self.assertEqual(harvest.state, Harvest.State.COMPLETED)
        self.assertGreaterEqual(harvest.elapsed_seconds, 60)
        client.get.assert_not_called()

    def test_monthly_schedule_keeps_anchor_day_after_short_month(self):
        start_date = timezone.make_aware(datetime(2024, 1, 31, 9, 0))
        schedule = Schedule.objects.create(
            frequency=Schedule.Frequency.MONTHLY,
            max_quantity=10,
            start_date=start_date,
            created_by=self.user,
        )
        ScheduleEvent.objects.create(
            schedule=schedule,
            scheduled_for=start_date,
            created_by=self.user,
        )
        february = _next_occurrence(schedule)
        self.assertEqual(february, timezone.make_aware(datetime(2024, 2, 29, 9, 0)))

        ScheduleEvent.objects.create(
            schedule=schedule,
            scheduled_for=february,
            created_by=self.user,
        )
        march = _next_occurrence(schedule)
        self.assertEqual(march, timezone.make_aware(datetime(2024, 3, 31, 9, 0)))
