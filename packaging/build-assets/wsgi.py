import os
import re
from pathlib import Path

import app as baby_tracker


GATEWAY_PREFIX = os.environ.get("BABY_TRACKER_GATEWAY_PREFIX", "/app/baby-tracker").rstrip("/")
GATEWAY_PREFIX_BYTES = GATEWAY_PREFIX.encode("ascii")
REWRITE_TYPES = (
    "text/html",
    "text/javascript",
    "application/javascript",
)


class GatewayPrefixMiddleware:
    """Remove the fnOS gateway prefix and prefix absolute browser URLs in responses."""

    def __init__(self, application, prefix):
        self.application = application
        self.prefix = prefix
        self.prefix_bytes = prefix.encode("ascii")

    def __call__(self, environ, start_response):
        original_path = environ.get("PATH_INFO", "")
        is_gateway_request = (
            original_path == self.prefix or original_path.startswith(self.prefix + "/")
        )
        if is_gateway_request:
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = original_path[len(self.prefix):] or "/"

        if not is_gateway_request:
            return self.application(environ, start_response)

        response_status = []
        response_headers = []

        def capture_start_response(status, headers, exc_info=None):
            response_status[:] = [status]
            response_headers[:] = list(headers)
            return lambda data: None

        app_iter = self.application(environ, capture_start_response)
        try:
            body = b"".join(app_iter)
        finally:
            close = getattr(app_iter, "close", None)
            if close is not None:
                close()

        status = response_status[0] if response_status else "500 Internal Server Error"
        headers = _rewrite_location_header(response_headers, self.prefix_bytes)
        content_type = _header_value(headers, "Content-Type").lower()
        if status[:3] != "304" and _should_rewrite_response(original_path, content_type):
            body = _rewrite_gateway_body(body, original_path, self.prefix_bytes)

        headers = [item for item in headers if item[0].lower() not in ("content-length", "etag")]
        headers.append(("Content-Length", str(len(body))))
        start_response(status, headers)
        return [body]


def _header_value(headers, name):
    wanted = name.lower()
    for header_name, header_value in headers:
        if header_name.lower() == wanted:
            return header_value
    return ""


def _rewrite_location_header(headers, prefix):
    rewritten = []
    for name, value in headers:
        if name.lower() == "location" and value.startswith("/") and not value.startswith("//"):
            if not (value == prefix.decode() or value.startswith(prefix.decode() + "/")):
                value = prefix.decode() + value
        rewritten.append((name, value))
    return rewritten


def _should_rewrite_response(path, content_type):
    if path.endswith("/static/manifest.json"):
        return True
    return any(content_type.startswith(item) for item in REWRITE_TYPES)


def _rewrite_gateway_body(body, path, prefix):
    for attribute in (b'href="/', b'src="/', b'action="/'):
        body = body.replace(attribute, attribute[:-2] + b'"' + prefix + b"/")

    for quote in (b"'", b'"', b"`"):
        for root in (b"/api/", b"/static/"):
            body = body.replace(quote + root, quote + prefix + root)

    body = re.sub(
        rb"(window\.location\.href\s*=\s*)(['\"])/([^'\"]*)\2",
        lambda match: (
            match.group(1)
            + match.group(2)
            + prefix
            + b"/"
            + match.group(3)
            + match.group(2)
        ),
        body,
    )

    if path.endswith("/static/js/spa.js"):
        for route in ("/", "/trends", "/vaccine", "/admin"):
            body = body.replace(
                ("        '%s':" % route).encode(),
                ("        '%s%s':" % (prefix.decode(), route)).encode(),
            )

    if path.endswith("/static/sw.js"):
        body = body.replace(b"    '/',", b"    '" + prefix + b"/',")

    if path.endswith("/static/manifest.json"):
        body = body.replace(
            b'"start_url": "/"',
            b'"start_url": "' + prefix + b'/"',
        )

    return body


data_dir = os.environ.get("BABY_TRACKER_DATA_DIR") or os.environ.get("TRIM_PKGVAR")
if data_dir:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    baby_tracker.app.config["DATABASE"] = str(Path(data_dir) / "baby.db")

application = GatewayPrefixMiddleware(baby_tracker.app, GATEWAY_PREFIX)
