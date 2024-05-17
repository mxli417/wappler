from twilio.rest import Client

from wappler.utils.log import get_logger

logger = get_logger(__name__)


def create_wapp_msg(
    account_sid: str,
    auth_token: str,
    msg_from: str,
    msg_to: str,
    msg_body: str = "Empty",
) -> str:
    """Twilio API client messaging wrapper

    Args:
        account_sid (str): Twilio account sid
        auth_token (str): Twilio account oauth token
        msg_from (str, optional): Whatsapp source number.
        msg_to (str, optional): Whatsapp destination number.
        msg_body (str, optional): Whatspp Twilio message payload. Defaults to "Empty".

    Returns:
        str: Twilio message SID
    """
    twclient = Client(account_sid, auth_token)
    if twclient is None:
        logger.error("Twilio api client init failed: %s" % twclient)
    try:
        message = client.messages.create(
            from_=msg_from,
            body=msg_body,
            to=msg_to,
        )
    except Exception as e:
        logger.error("Twilio api message client error: %s" % e)
        return None
    else:
        logger.info("Twilio api message client sent: %s" % msg_body)
        msg_sid = message.sid if message is not None else None
    return msg_sid
