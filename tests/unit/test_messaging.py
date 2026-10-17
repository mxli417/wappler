"""Twilio wrapper behavior without real outbound messages."""

from unittest.mock import Mock

import pytest

from wappler.wappchat import pchat


@pytest.mark.parametrize("failure", [False, True])
def test_twilio_send_and_error_propagation(monkeypatch, failure):
    client = Mock()
    client.messages.create.return_value.sid = "SMreply"
    if failure:
        client.messages.create.side_effect = RuntimeError("failed")
    monkeypatch.setattr(pchat, "Client", Mock(return_value=client))
    transport = Mock()
    monkeypatch.setattr(pchat, "TwilioHttpClient", Mock(return_value=transport))
    if failure:
        with pytest.raises(RuntimeError):
            pchat.create_wapp_msg("sid", "token", "from", "to", "hello")
    else:
        assert pchat.create_wapp_msg("sid", "token", "from", "to", "hello") == "SMreply"
        client.messages.create.assert_called_once_with(from_="from", to="to", body="hello")
    transport.session.close.assert_called_once()
