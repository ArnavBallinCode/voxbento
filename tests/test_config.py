import os
from unittest import mock
from portal.config import Settings

@mock.patch.dict(os.environ, {}, clear=True)
def test_settings_defaults():
    settings = Settings()
    assert settings.host == '127.0.0.1'
    assert settings.port == 8000
    assert settings.debug is True
    assert settings.secret_key == 'change-me'
    assert settings.api_key_encryption_key is None
    assert settings.booth_access_token == ''
    assert settings.default_jitsi_room == 'eventyay-stage-room'
    assert settings.jitsi_domain == 'jitsi.voxbento.com'
    assert settings.jitsi_base_url == ''
    assert settings.jitsi_internal_base == ''
    assert settings.mediamtx_whip_base == 'http://localhost:8889'
    assert settings.mediamtx_api_base == 'http://localhost:9997'
    assert settings.mediamtx_rtsp_base == 'rtsp://mediamtx:8554'
    assert settings.mediamtx_internal_base == ''
    assert settings.floor_bot_base == 'http://floor-bot:8080'
    assert settings.jwt_secret == ''
    assert settings.jwt_expiry_seconds == 86400
    assert settings.database_url == 'sqlite+aiosqlite:///./interpretation.db'
    assert settings.admin_password == ''
    assert settings.nvidia_function_id == ''

@mock.patch.dict(os.environ, {}, clear=True)
def test_effective_mediamtx_internal_base():
    # Test fallback to mediamtx_api_base
    settings = Settings(mediamtx_api_base="http://api.test:9997")
    assert settings.effective_mediamtx_internal_base == "http://api.test:9997"

    settings_override = Settings(mediamtx_internal_base="http://internal.mediamtx:9997")
    assert settings_override.effective_mediamtx_internal_base == "http://internal.mediamtx:9997"

@mock.patch.dict(os.environ, {}, clear=True)
def test_effective_jitsi_base_url():
    settings = Settings(jitsi_domain="custom.jitsi.org")
    assert settings.effective_jitsi_base_url == "http://custom.jitsi.org"

    settings_with_base = Settings(jitsi_base_url="https://override.jitsi.org")
    assert settings_with_base.effective_jitsi_base_url == "https://override.jitsi.org"

@mock.patch.dict(os.environ, {}, clear=True)
def test_effective_jitsi_internal_base():
    settings = Settings(jitsi_domain="test.jitsi")
    assert settings.effective_jitsi_internal_base == "http://test.jitsi"

    settings_override = Settings(jitsi_internal_base="http://internal.jitsi")
    assert settings_override.effective_jitsi_internal_base == "http://internal.jitsi"

@mock.patch.dict(os.environ, {}, clear=True)
def test_effective_jitsi_domain():
    settings = Settings(jitsi_domain="test.jitsi")
    assert settings.effective_jitsi_domain == "test.jitsi"

    settings_with_port = Settings(jitsi_base_url="http://test.jitsi:8080")
    assert settings_with_port.effective_jitsi_domain == "test.jitsi:8080"

@mock.patch.dict(os.environ, {}, clear=True)
def test_effective_jwt_secret():
    settings = Settings(secret_key="my-secret-key")
    assert settings.effective_jwt_secret == "my-secret-key"

    settings_jwt = Settings(secret_key="my-secret-key", jwt_secret="my-jwt-secret")
    assert settings_jwt.effective_jwt_secret == "my-jwt-secret"
