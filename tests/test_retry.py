import time
import logging
from unittest import mock

import pytest

from backend.core.retry import retry, _is_transient_exception

# Helper to count calls
class CallCounter:
    def __init__(self):
        self.count = 0
    def __call__(self, *args, **kwargs):
        self.count += 1
        return self.count

def test_retry_success_first_attempt():
    @retry()
    def always_ok():
        return 42
    assert always_ok() == 42

def test_retry_transient_then_success(monkeypatch):
    # Simulate a function that fails once with ConnectionError then succeeds
    attempts = []
    def flaky():
        attempts.append(True)
        if len(attempts) == 1:
            raise ConnectionError("transient")
        return "ok"
    # Patch time.sleep to avoid real waiting
    monkeypatch.setattr(time, "sleep", lambda s: None)
    result = retry()(flaky)()
    assert result == "ok"
    assert len(attempts) == 2

def test_retry_all_failures(monkeypatch):
    call_counter = CallCounter()
    def always_fail():
        call_counter()
        raise TimeoutError("still failing")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(TimeoutError):
        retry(attempts=3)(always_fail)()
    assert call_counter.count == 3

def test_retry_non_retryable(monkeypatch):
    def bad():
        raise ValueError("non‑transient")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(ValueError):
        retry()(bad)()

def test_backoff_and_jitter(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    call_seq = [ConnectionError("first"), ConnectionError("second"), None]
    def flaky():
        exc = call_seq.pop(0)
        if exc:
            raise exc
        return "done"
    result = retry(attempts=3, backoff_factor=0.1, jitter=0.05)(flaky)()
    assert result == "done"
    # Should have two sleep calls with increasing base delay (0.1, 0.2) plus jitter
    assert len(sleeps) == 2
    assert sleeps[0] >= 0.1 and sleeps[0] <= 0.15
    assert sleeps[1] >= 0.2 and sleeps[1] <= 0.25

def test_is_transient_exception_detection():
    class DummyExc(Exception):
        response = None
    # Direct transient type
    assert _is_transient_exception(TimeoutError(), (TimeoutError,))
    # HTTP response 429
    resp = mock.Mock(status_code=429)
    exc = Exception()
    exc.response = resp
    assert _is_transient_exception(exc, ())
    # HTTP response 502
    resp2 = mock.Mock(status_code=502)
    exc2 = Exception()
    exc2.response = resp2
    assert _is_transient_exception(exc2, ())
    # Non‑transient status
    resp3 = mock.Mock(status_code=404)
    exc3 = Exception()
    exc3.response = resp3
    assert not _is_transient_exception(exc3, ())

def test_google_sheets_manager_get_client_retry(monkeypatch, caplog):
    from backend.sheets.client import GoogleSheetsManager
    # Force a transient failure on first call to _resolve_credentials
    call_counter = {'calls': 0}
    def failing_resolve(self):
        call_counter['calls'] += 1
        if call_counter['calls'] == 1:
            raise ConnectionError("transient auth error")
        class DummyCreds:
            pass
        return DummyCreds()
    monkeypatch.setattr(GoogleSheetsManager, "_resolve_credentials", failing_resolve)
    # Patch gspread.authorize to a lambda that returns a mock client
    mock_client = mock.Mock()
    monkeypatch.setattr("gspread.authorize", lambda creds: mock_client)
    caplog.set_level(logging.WARNING)
    manager = GoogleSheetsManager(service_account_file="/invalid/path.json")
    client = manager.get_client()
    assert client is mock_client
    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any("Transient error" in rec.getMessage() for rec in warnings)
    assert call_counter['calls'] == 2
