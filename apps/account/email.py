import resend
from django.conf import settings
from requests import RequestException


class EmailDeliveryError(Exception):
    pass


def send_email(to_email, subject, html_content):
    if not settings.RESEND_API_KEY:
        raise EmailDeliveryError("El envío de correo no está configurado.")

    resend.api_key = settings.RESEND_API_KEY
    try:
        return resend.Emails.send({
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        })
    except (resend.exceptions.ResendError, RequestException) as error:
        raise EmailDeliveryError(f"No se pudo entregar el correo: {error}") from error
