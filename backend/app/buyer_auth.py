
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import Header

from .security import ApiError


def _verificar_token(token: str) -> dict:
    url = os.environ.get(
        "SUPABASE_URL", ""
    ).rstrip("/")

    api_key = os.environ.get(
        "SUPABASE_PUBLISHABLE_KEY", ""
    )

    if not url.startswith("https://") or not api_key:
        raise ApiError(
            503,
            "AUTH_NOT_CONFIGURED",
            "Autenticacion no configurada",
        )

    req = urllib.request.Request(
        url + "/auth/v1/user",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            usuario = json.load(response)

    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ApiError(
                401,
                "UNAUTHORIZED",
                "Sesion no valida o expirada",
            ) from exc

        raise ApiError(
            503,
            "AUTH_UNAVAILABLE",
            "No se pudo verificar la sesion",
        ) from exc

    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(
            503,
            "AUTH_UNAVAILABLE",
            "Servicio de autenticacion no disponible",
        ) from exc

    if not isinstance(usuario, dict) or not usuario.get("id"):
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "Usuario no valido",
        )

    return usuario


async def comprador_autenticado(
    authorization: str | None = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "Debes iniciar sesion para comprar",
        )

    token = authorization[7:].strip()

    if not token:
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "Token de sesion requerido",
        )

    return await asyncio.to_thread(_verificar_token, token)
