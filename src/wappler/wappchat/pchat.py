"""Outbound WhatsApp messaging through the Twilio REST API."""

from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client


def create_wapp_msg(
    account_sid: str,
    auth_token: str,
    msg_from: str,
    msg_to: str,
    msg_body: str = "Empty",
) -> str:
    """Send a WhatsApp reply and return the accepted message SID.

    Args:
        account_sid: Twilio account SID.
        auth_token: Twilio account auth token.
        msg_from: Registered sender, including the whatsapp: prefix.
        msg_to: Recipient, including the whatsapp: prefix.
        msg_body: Reply text.

    Returns:
        Twilio message SID. Acceptance does not confirm delivery.

    Raises:
        twilio.base.exceptions.TwilioRestException: Twilio rejects the message.
        RuntimeError: Twilio returns no message identifier.
    """
    http_client = TwilioHttpClient(timeout=15)
    try:
        client = Client(account_sid, auth_token, http_client=http_client)
        message = client.messages.create(from_=msg_from, body=msg_body, to=msg_to)
    finally:
        if http_client.session:
            http_client.session.close()
    if not message.sid:
        raise RuntimeError("Twilio returned no message SID")
    return message.sid
