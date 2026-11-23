
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
import uuid

logger = logging.getLogger(__name__)


class BillingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def enviar_factura(
    order_id: str,
    items: list[dict],
    total_cents: int,
) -> dict:
    base_url = os.environ.get("BILLING_BASE_URL", "").rstrip("/")
    token = os.environ.get("BILLING_TOKEN", "")

    if not base_url.startswith("https://") or not token:
        raise BillingError(0, "Configuracion de facturacion incompleta")

    try:
        order_id = str(uuid.UUID(order_id))
    except ValueError as exc:
        raise BillingError(0, "ID de pedido invalido") from exc

    datos = {
        "order_id": order_id,
        "currency": "PEN",
        "items": items,
        "total_cents": total_cents,
    }

    solicitud = urllib.request.Request(
        base_url + "/invoices",
        data=json.dumps(datos).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Billing-Token": token,
            "Idempotency-Key": order_id,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=15) as respuesta:
            resultado = json.load(respuesta)
            logger.info(
                "Factura emitida para pedido=%s HTTP=%s",
                order_id,
                respuesta.status,
            )
            return resultado

    except urllib.error.HTTPError as exc:
        logger.warning(
            "Facturacion rechazada pedido=%s HTTP=%s",
            order_id,
            exc.code,
        )
        raise BillingError(
            exc.code,
            "Supabase rechazo la solicitud",
        ) from exc

    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "Servicio de facturacion no disponible pedido=%s",
            order_id,
        )
        raise BillingError(
            0,
            "Error de comunicacion con Supabase",
        ) from exc


async def enviar_factura_async(
    order_id: str,
    items: list[dict],
    total_cents: int,
) -> dict:
    return await asyncio.to_thread(
        enviar_factura,
        order_id,
        items,
        total_cents,
    )
