"""Tests for structlog configuration."""

import json
import logging

import structlog

from helprs.core.middleware import configure_logging


def test_structlog_produces_json_with_expected_fields(capfd):
    configure_logging()

    # Set up logging to actually write to stderr
    logging.basicConfig(format="%(message)s", stream=None, level=logging.INFO, force=True)

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-123")

    log = structlog.get_logger()
    log.info("test_event", key="value")

    captured = capfd.readouterr()
    # structlog with stdlib logger goes to stderr
    output = captured.err.strip()
    if not output:
        output = captured.out.strip()

    # Find the JSON line
    for line in output.splitlines():
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    else:
        # If we can't parse JSON from captured output, the JSON renderer is working
        # but output is being captured differently. Verify via structlog internals.
        import io

        string_io = io.StringIO()
        handler = logging.StreamHandler(string_io)
        handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        log.info("test_event_2", key="value2")

        root_logger.removeHandler(handler)
        raw = string_io.getvalue().strip()
        data = json.loads(raw)

    assert data["event"] in ("test_event", "test_event_2")
    assert data["request_id"] == "test-123"
    assert "level" in data
    assert "timestamp" in data
