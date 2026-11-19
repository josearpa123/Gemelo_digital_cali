"""Same-origin access policy for the single-process demo server."""

import asyncio
import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

ROLES = {"viewer": 1, "operator": 2, "admin": 3}
COOKIE = "gemelo_session"
SESSION_SECONDS = 8 * 3600
BODY_LIMIT = 8192
ADMIN_ROUTES = {"/api/llm/key", "/api/llm/test"}
POLICY = (
    "default-src 'self'; script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: "
    "https://unpkg.com https://*.tile.openstreetmap.org; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


def require(scope, role: str) -> None:
    if ROLES.get(scope.get("gemelo_role"), 0) < ROLES[role]:
        raise HTTPException(403, "Permiso insuficiente")


def demo_faults() -> bool:
    return os.environ.get("DEMO_FAULTS") == "1"


def csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.signing_key = secrets.token_bytes(32)

    def _signature(self, data: str) -> str:
        return hmac.new(self.signing_key, data.encode(), hashlib.sha256).hexdigest()

    def _session(self, headers):
        try:
            cookie = SimpleCookie(headers.get("cookie", ""))
            value = cookie[COOKIE].value
            data, signature = value.rsplit(".", 1)
            session, role, expires = data.split(".")
            if (
                hmac.compare_digest(self._signature(data).encode(), signature.encode())
                and int(expires) > time.time()
                and role in ROLES
            ):
                return session, role, int(expires)
        except (CookieError, KeyError, ValueError):
            pass
        return None

    @staticmethod
    def _basic_role(headers):
        try:
            scheme, value = headers.get("authorization", "").split()
            if scheme.lower() != "basic":
                return None
            role, password = base64.b64decode(value, validate=True).split(b":", 1)
            role = role.decode("ascii")
        except (ValueError, UnicodeError, binascii.Error):
            return None
        configured = os.environ.get(f"DEMO_{role.upper()}_PASSWORD") if role in ROLES else None
        if (
            configured
            and len(configured) >= 16
            and hmac.compare_digest(password, configured.encode())
        ):
            return role
        return None

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        path = scope["path"]
        method = scope.get("method")
        public = kind == "http" and path == "/health" and method == "GET"
        local = os.environ.get("DEMO_ACCESS", "local") == "local"
        host = headers.get("host", "")
        scheme = "https" if scope["scheme"] in {"https", "wss"} else "http"
        try:
            hostname = urlsplit(f"//{host}").hostname
        except ValueError:
            hostname = None
        origin = os.environ.get("DEMO_ORIGIN") or f"{scheme}://{host}"
        mutating = kind == "http" and method not in {"GET", "HEAD", "OPTIONS"}

        async def reject(status, message, challenge=False):
            if kind == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            response_headers = {"Cache-Control": "no-store"}
            if challenge:
                response_headers["WWW-Authenticate"] = 'Basic realm="Gemelo Digital"'
            await JSONResponse({"detail": message}, status_code=status, headers=response_headers)(
                scope, receive, send
            )

        if not public:
            loopback = hostname in {"localhost", "127.0.0.1", "::1"}
            if local and not loopback:
                await reject(403, "El modo local requiere una dirección de loopback")
                return
            if not local:
                configured = urlsplit(origin)
                if configured.netloc != host or (
                    not loopback
                    and (not os.environ.get("DEMO_ORIGIN") or configured.scheme != "https")
                ):
                    await reject(403, "Usa el origen HTTPS configurado para la demo")
                    return
        if (mutating or kind == "websocket") and (
            headers.get("origin", origin) != origin
            or headers.get("sec-fetch-site") in {"cross-site", "same-site"}
        ):
            await reject(403, "Origen no permitido")
            return

        session = self._session(headers) if not public else None
        new_cookie = None
        if not public and not session:
            role = "admin" if local else self._basic_role(headers)
            if not role or (not local and kind == "websocket"):
                await reject(401, "Inicia sesión en el panel", challenge=True)
                return
            session = (secrets.token_urlsafe(24), role, int(time.time()) + SESSION_SECONDS)
            data = ".".join(map(str, session))
            secure = "; Secure" if origin.startswith("https://") else ""
            new_cookie = (
                f"{COOKIE}={data}.{self._signature(data)}; Path=/; "
                f"Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Strict{secure}"
            )

        if session:
            scope["gemelo_session"], scope["gemelo_role"], scope["gemelo_expires"] = session
            minimum = (
                "admin"
                if path in ADMIN_ROUTES
                else "operator"
                if mutating and path != "/api/assistant"
                else "viewer"
            )
            if ROLES[session[1]] < ROLES[minimum]:
                await reject(403, "Permiso insuficiente")
                return

        if mutating:
            body = bytearray()
            try:
                async with asyncio.timeout(3):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > BODY_LIMIT:
                            await reject(413, "Cuerpo demasiado grande")
                            return
                        body.extend(chunk)
                        if not message.get("more_body"):
                            break
            except TimeoutError:
                await reject(408, "Tiempo de lectura agotado")
                return
            original_receive = receive
            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await original_receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            receive = replay

        async def send_headers(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"content-security-policy", POLICY.encode()),
                ]
                if path.startswith("/api/") or new_cookie or path in {"/", "/index.html"}:
                    extra.append((b"cache-control", b"no-store"))
                if new_cookie:
                    extra.append((b"set-cookie", new_cookie.encode()))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_headers)
