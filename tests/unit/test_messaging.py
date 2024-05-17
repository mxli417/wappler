import os

import pytest

from wappler.utils import config
from wappler.wappchat.pchat import create_wapp_msg


class TestMessaging:
    @pytest.mark.skipif(
        os.getenv("ENVIRONMENT") not in ["twilio-active"],
        reason="Skipping OpenAI API call test - wrong environment",
    )
    def test_twilio_out(self):
        assert (
            create_wapp_msg(
                account_sid=os.getenv("TWILIO_SID"),
                auth_token=os.getenv("TWILIO_TOKEN"),
                msg_from=os.getenv("TWILIO_TEST_MSG_FROM"),
                msg_to=os.getenv("TWILIO_TEST_MSG_TO"),
                msg_body="Test test test",
            )
            is not None
        )
