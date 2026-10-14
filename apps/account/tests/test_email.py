from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

import resend

from apps.account.email import EmailDeliveryError, send_email


class ResendEmailTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY="re_test_key",
        DEFAULT_FROM_EMAIL="Biblioteca <noreply@example.org>",
    )
    @patch("apps.account.email.resend.Emails.send")
    def test_sends_html_using_resend_sdk(self, send):
        send.return_value = {"id": "email_123"}

        response = send_email(
            "reader@example.org",
            "Invitación",
            "<p>Bienvenida</p>",
        )

        self.assertEqual(response, {"id": "email_123"})
        send.assert_called_once_with({
            "from": "Biblioteca <noreply@example.org>",
            "to": ["reader@example.org"],
            "subject": "Invitación",
            "html": "<p>Bienvenida</p>",
        })
        self.assertEqual(resend.api_key, "re_test_key")

    @override_settings(RESEND_API_KEY="")
    def test_reports_missing_api_key(self):
        with self.assertRaises(EmailDeliveryError):
            send_email("reader@example.org", "Asunto", "<p>Contenido</p>")

    @override_settings(RESEND_API_KEY="re_test_key")
    @patch(
        "apps.account.email.resend.Emails.send",
        side_effect=resend.exceptions.ResendError(
            500,
            "internal_server_error",
            "provider error",
            "Check the Resend configuration.",
        ),
    )
    def test_wraps_resend_api_errors(self, _send):
        with self.assertRaisesRegex(EmailDeliveryError, "provider error"):
            send_email("reader@example.org", "Asunto", "<p>Contenido</p>")
