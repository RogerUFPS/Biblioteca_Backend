import httpx
from django.conf import settings


class EmailDeliveryError(Exception):
    pass


def send_email(to, subject, text):
    api_key = settings.RESEND_API_KEY
    if not api_key:
        raise EmailDeliveryError("El envío de correo no está configurado.")
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "text": text,
            },
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise EmailDeliveryError("No se pudo entregar el correo.") from error
