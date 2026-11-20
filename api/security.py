"""Same-origin access policy for the single-process demo server."""

import asyncio
import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, RedirectResponse

ROLES = {"viewer": 1, "operator": 2, "admin": 3}
COOKIE = "gemelo_session"
SESSION_SECONDS = 8 * 3600
BODY_LIMIT = 8192
ADMIN_ROUTES = {"/api/llm/key", "/api/llm/test"}
LOGIN_ASSETS = {"/style.css", "/login.css", "/login.js"}
POLICY = (
    "default-src 'self'; script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: "
    "https://unpkg.com https://*.tile.openstreetmap.org; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
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
        self.login_attempts: dict[str, deque[float]] = {}

    def _signature(self, data: str) -> str:
        return hmac.new(self.signing_key, data.encode(), hashlib.sha256).hexdigest()

    def _session(self, headers, cookie_name):
        try:
            cookie = SimpleCookie(headers.get("cookie", ""))
            value = cookie[cookie_name].value
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
    def _role(role: str, password: bytes):
        configured = os.environ.get(f"DEMO_{role.upper()}_PASSWORD") if role in ROLES else None
        if (
            configured
            and len(configured) >= 16
            and hmac.compare_digest(password, configured.encode())
        ):
            return role
        return None

    def _basic_role(self, headers):
        try:
            scheme, value = headers.get("authorization", "").split()
            if scheme.lower() != "basic":
                return None
            role, password = base64.b64decode(value, validate=True).split(b":", 1)
            role = role.decode("ascii")
        except (ValueError, UnicodeError, binascii.Error):
            return None
        return self._role(role, password)

    def _new_session(self, role, origin, cookie_name):
        session = (secrets.token_urlsafe(24), role, int(time.time()) + SESSION_SECONDS)
        data = ".".join(map(str, session))
        secure = "; Secure" if origin.startswith("https://") else ""
        cookie = (
            f"{cookie_name}={data}.{self._signature(data)}; Path=/; "
            f"Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Strict{secure}"
        )
        return session, cookie

    def _login_allowed(self, client):
        now = time.monotonic()
        cutoff = now - 60
        for key, attempts in list(self.login_attempts.items()):
            if attempts[-1] <= cutoff:
                del self.login_attempts[key]
        if client not in self.login_attempts and len(self.login_attempts) >= 512:
            return False
        attempts = self.login_attempts.setdefault(client, deque())
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= 8:
            return False
        attempts.append(now)
        return True

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
        login_page = kind == "http" and path == "/login" and method in {"GET", "HEAD"}
        login_submit = kind == "http" and path == "/login" and method == "POST"
        login_asset = kind == "http" and path in LOGIN_ASSETS and method in {"GET", "HEAD"}

        async def reject(status, message):
            if kind == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            response_headers = {"Cache-Control": "no-store"}
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
            headers.get("origin", "" if login_submit else origin) != origin
            or headers.get("sec-fetch-site") in {"cross-site", "same-site"}
        ):
            await reject(403, "Origen no permitido")
            return

        # Browsers share cookies between ports on the same host.
        cookie_name = f"{COOKIE}_{hashlib.sha256(origin.encode()).hexdigest()[:12]}"
        session = self._session(headers, cookie_name) if not public else None
        new_cookie = None
        if ((local or session) and login_page) or (local and login_submit):
            await RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})(
                scope, receive, send
            )
            return
        if not (public or login_page or login_submit or login_asset or session):
            if not local and kind == "http" and path in {"/", "/index.html"} and not mutating:
                await RedirectResponse(
                    "/login", status_code=303, headers={"Cache-Control": "no-store"}
                )(scope, receive, send)
                return
            role = "admin" if local else self._basic_role(headers)
            if not role or (not local and kind == "websocket"):
                await reject(401, "Inicia sesión en el panel")
                return
            session, new_cookie = self._new_session(role, origin, cookie_name)

        if session and not login_submit:
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
            if login_submit:
                origin_type = headers.get("content-type", "").split(";", 1)[0]
                if origin_type != "application/x-www-form-urlencoded":
                    await reject(415, "Formato de inicio de sesión inválido")
                    return
                client = (scope.get("client") or ("unknown",))[0]
                location = "/login?error=limit"
                if self._login_allowed(client):
                    try:
                        fields = parse_qs(body.decode(), strict_parsing=True, max_num_fields=2)
                        (username,) = fields["username"]
                        (password,) = fields["password"]
                        role = self._role(username, password.encode())
                    except (KeyError, ValueError):
                        role = None
                    if role:
                        _, new_cookie = self._new_session(role, origin, cookie_name)
                        location = "/"
                    else:
                        location = "/login?error=credentials"
                response_headers = {"Cache-Control": "no-store"}
                if new_cookie:
                    response_headers["Set-Cookie"] = new_cookie
                await RedirectResponse(location, status_code=303, headers=response_headers)(
                    scope, receive, send
                )
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
                if path.startswith("/api/") or new_cookie or path in {"/", "/index.html", "/login"}:
                    extra.append((b"cache-control", b"no-store"))
                if new_cookie:
                    extra.append((b"set-cookie", new_cookie.encode()))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_headers)
