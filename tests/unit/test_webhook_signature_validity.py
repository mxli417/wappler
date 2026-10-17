"""Signature, validation and HTTP regression tests using an in-process app."""

import pytest


def test_public_https_signature_behind_http_proxy(signed_post, form, vendors, drain):
    response = signed_post(form)
    assert response.status_code == 200
    assert response.text == "<Response/>"
    assert response.headers["content-type"].startswith("application/xml")
    vendors[0].assert_not_called()
    drain()
    vendors[0].assert_called_once()
    vendors[1].assert_called_once()


@pytest.mark.parametrize("signature", ["", "invalid"])
def test_invalid_signature(client, form, vendors, signature):
    response = client.post("/v0/twilio", data=form, headers={"X-Twilio-Signature": signature})
    assert response.status_code == 403
    vendors[0].assert_not_called()
    vendors[1].assert_not_called()


def test_wrong_public_url(signed_post, form, vendors):
    assert signed_post(form, "http://testserver/v0/twilio").status_code == 403
    vendors[1].assert_not_called()


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("From", "whatsapp:+15550000003", 403),
        ("From", "", 400),
        ("To", "whatsapp:+15550000003", 403),
        ("AccountSid", "ACother", 403),
        ("MessageSid", "", 400),
        ("NumMedia", "-1", 400),
        ("NumMedia", "invalid", 400),
        ("MediaUrl0", "", 400),
    ],
)
def test_invalid_fields(signed_post, form, vendors, field, value, status):
    form[field] = value
    assert signed_post(form).status_code == status
    vendors[0].assert_not_called()
    vendors[1].assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"NumMedia": "0"},
        {"MediaContentType0": "image/jpeg"},
        {"NumMedia": "2"},
    ],
)
def test_non_audio_gets_help(signed_post, form, vendors, updates, drain):
    form.update(updates)
    assert signed_post(form).status_code == 200
    drain()
    vendors[0].assert_not_called()
    assert "audio attachment" in vendors[1].call_args.kwargs["msg_body"]


def test_no_media_key_for_text(signed_post, form, vendors):
    form["NumMedia"] = "0"
    del form["MediaUrl0"]
    assert signed_post(form).status_code == 200
    vendors[0].assert_not_called()


@pytest.mark.parametrize("vendor", [0, 1])
def test_upstream_failure_is_recorded(signed_post, client, form, vendors, vendor, capsys, drain):
    vendors[vendor].side_effect = RuntimeError("private-message-and-token")
    response = signed_post(form)
    assert response.status_code == 200
    drain()
    assert "private-message-and-token" not in response.text + capsys.readouterr().out
    state = "failed" if vendor == 0 else "uncertain"
    assert client.app.state.store.snapshot()["jobs"] == {state: 1}
    if vendor == 0:
        vendors[1].assert_not_called()


def test_liveness_and_stats(client, signed_post, form, vendors, drain):
    assert client.get("/heartbeat").json() == {"status": "ok"}
    assert client.get("/stats").status_code == 404
    assert client.get("/ready").status_code == 200
    signed_post(form)
    drain()
    assert client.app.state.store.snapshot()["jobs"] == {"succeeded": 1}


def test_wrong_content_type(client):
    assert client.post("/v0/twilio", json={}).status_code == 415


def test_long_reply_is_bounded(signed_post, form, vendors, drain):
    vendors[0].return_value = "a" * 5000
    assert signed_post(form).status_code == 200
    drain()
    body = vendors[1].call_args.kwargs["msg_body"]
    assert len(body) <= 1500
    assert body.endswith("[Transcript shortened]")
