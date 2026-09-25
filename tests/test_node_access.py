"""Credentials for the Sentinel grid: added only at connect time, never leaked."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prahari.node import access
from prahari.node.catalogue import CatalogueAuthError, fetch_catalogue, sanitise
from prahari.common.contracts import CameraInfo

RTSP = "rtsp://103.250.160.189:8554/stream/cam01"


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv(access.USER_ENV, "alice@example.com")
    monkeypatch.setenv(access.PASSWORD_ENV, "p@ss:w/rd")
    monkeypatch.delenv(access.COOKIE_ENV, raising=False)
    monkeypatch.delenv(access.TEMPLATE_ENV, raising=False)


def test_email_at_sign_is_percent_encoded():
    out = access.with_credentials(RTSP)
    assert out == "rtsp://alice%40example.com:p%40ss%3Aw%2Frd@103.250.160.189:8554/stream/cam01"


def test_existing_credentials_are_left_alone():
    url = "rtsp://bob%40x.com:other@103.250.160.189:8554/stream/cam01"
    assert access.with_credentials(url) == url


def test_hls_gets_no_credentials_but_whep_does():
    assert access.with_credentials("https://cctv.corp8.cloud/cam01/index.m3u8") == \
        "https://cctv.corp8.cloud/cam01/index.m3u8"
    assert "alice%40example.com" in access.with_credentials(
        "http://103.250.160.189:8889/stream/cam01/whep")


def test_no_user_means_url_unchanged(monkeypatch):
    monkeypatch.delenv(access.USER_ENV)
    assert access.with_credentials(RTSP) == RTSP


def test_strip_credentials_round_trip():
    assert access.strip_credentials(access.with_credentials(RTSP)) == RTSP


def test_scrub_removes_password_from_error_text():
    err = f"[Errno 13] Permission denied: '{access.with_credentials(RTSP)}'"
    out = access.scrub(err)
    assert "p@ss" not in out and "p%40ss" not in out and "alice" not in out
    assert "103.250.160.189" in out


def test_sanitise_strips_catalogue_credentials_and_fills_template(monkeypatch):
    monkeypatch.setenv(access.TEMPLATE_ENV, "rtsp://103.250.160.189:8554/stream/{id}")
    cams = sanitise([
        CameraInfo(id="cam01", rtsp_url="rtsp://u:secret@103.250.160.189:8554/stream/cam01"),
        CameraInfo(id="cam02"),
    ])
    assert cams[0].rtsp_url == RTSP
    assert cams[1].rtsp_url == "rtsp://103.250.160.189:8554/stream/cam02"


def test_catalogue_from_saved_file(tmp_path):
    f = tmp_path / "cameras.json"
    f.write_text(json.dumps([{"id": "cam01", "rtsp": "rtsp://u:pw@1.2.3.4:8554/stream/cam01"}]))
    cams = fetch_catalogue(str(f))
    assert [c.id for c in cams] == ["cam01"]
    assert cams[0].rtsp_url == "rtsp://1.2.3.4:8554/stream/cam01"
    assert fetch_catalogue(f.as_uri())[0].id == "cam01"


def test_login_redirect_gives_a_clear_error():
    def handler(req):
        if req.url.path == "/cameras.json":
            return httpx.Response(302, headers={"location": "/auth/login"})
        return httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"})
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(CatalogueAuthError, match="save it as a file"):
        fetch_catalogue("https://cctv.corp8.cloud/cameras.json", client=client)


def test_cookie_is_sent_when_configured(monkeypatch):
    monkeypatch.setenv(access.COOKIE_ENV, "session=abc")
    seen = {}
    def handler(req):
        seen["cookie"] = req.headers.get("cookie")
        return httpx.Response(200, json=[{"id": "cam01"}])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetch_catalogue("https://cctv.corp8.cloud/cameras.json", client=client)
    assert seen["cookie"] == "session=abc"


def test_registry_never_stores_credentials(tmp_path):
    from prahari.registry import cameras
    from prahari.registry.db import Store
    store = Store(tmp_path / "r.db")
    cameras.upsert(store, [{"id": "cam01", "rtsp_url": "rtsp://u:secret@1.2.3.4/stream/cam01"}],
                   source="manual")
    assert "secret" not in (cameras.get(store, "cam01")["rtsp_url"] or "")
