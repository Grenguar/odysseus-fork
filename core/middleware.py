# src/middleware.py
# Shared middleware, decorators, and request helpers

import os
import secrets

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# Per-process token that lets the in-app tool layer hit admin-gated
# routes via HTTP loopback (the agent's tool calls don't carry the
# admin user's session cookie). Set once at import; tools read the
# same value from this module. Never persisted or exposed externally.
INTERNAL_TOOL_TOKEN = os.environ.get("ODYSSEUS_INTERNAL_TOKEN") or secrets.token_hex(32)
INTERNAL_TOOL_HEADER = "X-Odysseus-Internal-Token"


def require_admin(request: Request):
    """Raise 403 if the current user isn't an admin.
    Allows access when auth is explicitly disabled, or when the request carries
    the in-process internal-tool token used by loopback agent tools.
    """
    # In-process bypass for tool-layer loopback calls. Two paths:
    # (a) header-direct (caller set X-Odysseus-Internal-Token), or
    # (b) the auth middleware already validated the token and stamped
    #     request.state.current_user = "internal-tool".
    try:
        hdr = request.headers.get(INTERNAL_TOOL_HEADER)
        if hdr and secrets.compare_digest(hdr, INTERNAL_TOOL_TOKEN):
            return
        if getattr(request.state, "current_user", None) == "internal-tool":
            return
    except Exception:
        pass

    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if os.getenv("AUTH_ENABLED", "true").lower() == "false":
        return
    if not auth_mgr or not auth_mgr.is_configured:
        raise HTTPException(403, "Admin only")
    user = getattr(request.state, "current_user", None)
    if not user or not auth_mgr.is_admin(user):
        raise HTTPException(403, "Admin only")


class SameOriginCsrfMiddleware(BaseHTTPMiddleware):
    """Origin/Referer-based CSRF defense for cookie-authenticated state-
    changing requests.

    Why this and not double-submit cookie tokens? The app ships ~50 routes
    that mutate state via cookie auth; adding a token-header dance to all
    of them needs coordinated frontend changes. Origin/Referer checks are
    purely server-side, do not require any frontend cooperation, and the
    OWASP CSRF cheatsheet treats them as a sufficient primary defense.

    Logic:
        * GET/HEAD/OPTIONS pass through (safe by spec).
        * Bearer-token requests pass through (no ambient cookie → no CSRF).
        * Internal-tool loopback requests pass through (already path-
          restricted and token-validated by AuthMiddleware).
        * Auth-exempt + webhook-trigger paths pass through (their own
          auth model is path-or-token, not a cookie).
        * For everything else (cookie-authenticated POST/PUT/DELETE/PATCH)
          we require the Origin or Referer header to match the request's
          Host (or the Origin/Referer is the same scheme+host as the
          app's effective origin). Missing both => 403.

    Browsers attach Origin to all cross-origin POSTs and to same-origin
    POSTs in modern Chrome/Firefox/Safari, so the same-origin invariant
    holds. The Referer fallback covers the rare browser that omits Origin.
    """

    _SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    # Routes whose auth model is path-embedded or first-touch: they don't
    # hold a session cookie yet, so CSRF doesn't apply. Keep in sync with
    # the auth-exempt set in app.py and with paths whose handler validates
    # a per-request token of its own (webhook trigger).
    _EXEMPT_EXACT = frozenset({
        "/api/auth/setup",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/signup",
    })
    _EXEMPT_PREFIXES = ("/static/",)
    import re as _re_mod
    _EXEMPT_PATTERNS = (
        _re_mod.compile(r"^/api/tasks/[^/]+/webhook/[^/]+/?$"),
    )

    def _path_exempt(self, path: str) -> bool:
        if path in self._EXEMPT_EXACT:
            return True
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return True
        return any(p.match(path) for p in self._EXEMPT_PATTERNS)

    @staticmethod
    def _normalize_origin(value: str) -> str:
        """Return scheme://host[:port], lowercased, no trailing path."""
        if not value:
            return ""
        from urllib.parse import urlsplit
        try:
            parts = urlsplit(value)
        except Exception:
            return ""
        if not parts.scheme or not parts.netloc:
            return ""
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"

    def _expected_origins(self, request: Request) -> set:
        """Origins that count as same-site for this request."""
        candidates = set()
        host = request.headers.get("host", "")
        if host:
            # Trust the connection's actual scheme — falls back to https
            # behind a TLS-terminating proxy that sets X-Forwarded-Proto.
            scheme = request.url.scheme or "http"
            fp = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
            if fp in ("http", "https"):
                scheme = fp
            candidates.add(f"{scheme.lower()}://{host.lower()}")
        # Allow operators to whitelist additional origins (reverse proxy
        # hostname, alt domain) via the existing ALLOWED_ORIGINS env.
        extra = os.getenv("ALLOWED_ORIGINS", "")
        for o in extra.split(","):
            n = self._normalize_origin(o)
            if n:
                candidates.add(n)
        return candidates

    async def dispatch(self, request: Request, call_next):
        method = (request.method or "GET").upper()
        if method in self._SAFE_METHODS:
            return await call_next(request)

        path = request.url.path or ""
        if self._path_exempt(path):
            return await call_next(request)

        # Bearer-token callers don't carry an ambient session cookie, so
        # no browser will silently attach credentials cross-site → no
        # CSRF risk.
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            return await call_next(request)

        # In-process agent loopback: protected by INTERNAL_TOOL_TOKEN +
        # loopback-only client check in AuthMiddleware. Skip CSRF here so
        # we don't break the tool layer.
        try:
            hdr = request.headers.get(INTERNAL_TOOL_HEADER)
            if hdr and secrets.compare_digest(hdr, INTERNAL_TOOL_TOKEN):
                return await call_next(request)
        except Exception:
            pass

        # Only enforce when a session cookie is actually present. Without
        # a cookie, AuthMiddleware will reject the request itself; no need
        # to also block on CSRF and produce confusing error pairs.
        if not request.cookies:
            return await call_next(request)
        # Check Origin first, then Referer as a fallback for the small
        # set of clients that strip Origin.
        expected = self._expected_origins(request)
        origin = self._normalize_origin(request.headers.get("origin", ""))
        referer = self._normalize_origin(request.headers.get("referer", ""))
        if origin and origin in expected:
            return await call_next(request)
        if referer and referer in expected:
            return await call_next(request)
        # If neither header is present at all, this is almost always a
        # non-browser tool (curl) without an API token — treat that as a
        # misconfiguration rather than silently allowing it through.
        if not origin and not referer:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={
                    "error": "CSRF: missing Origin/Referer on cookie-authenticated request. "
                             "Use an API token (Authorization: Bearer ody_...) for non-browser clients."
                },
            )
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=403,
            content={"error": "CSRF: Origin/Referer does not match app origin."},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate a per-request nonce for inline scripts
        nonce = secrets.token_hex(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)
        path = request.url.path

        # Tool render endpoints are served inside iframes — allow framing by self
        is_tool_render = path.startswith("/api/tools/") and path.endswith("/render")
        # Visual report pages are self-contained HTML — need inline scripts + external images
        is_report = path.startswith("/api/research/report/")

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"

        if is_report:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'"
            )
        elif is_tool_render:
            # Tool iframe content: skip all framing headers — the iframe's
            # sandbox="allow-scripts" attribute provides isolation.
            # Don't overwrite the route's own restrictive CSP either.
            pass
        else:
            response.headers["X-Frame-Options"] = "DENY"
            # NOTE: `style-src 'unsafe-inline'` is intentionally retained.
            # `static/index.html` and `static/login.html` ship inline <style>
            # blocks, and several JS modules build runtime `style=""` attrs.
            # Migrating to nonce-only requires templating the HTML files +
            # auditing every JS-set style attribute. Since inline styles
            # don't execute script, the residual risk is visual-only.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "img-src 'self' data: blob:; "
                "media-src 'self' blob:; "
                "connect-src 'self'; "
                "frame-src 'self'; "
                "frame-ancestors 'none'"
            )
        return response
