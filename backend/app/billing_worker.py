
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select

from .billing import BillingError, enviar_factura_async
from .db import utcnow
from .models import BillingJob, Order

logger = logging.getLogger(__name__)


async def procesar_factura(database):
    ahora = utcnow()

    async with database.session_factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(BillingJob)
                    .where(
                        or_(
                            BillingJob.status.in_(["pending", "retry"]),
                            BillingJob.status == "processing",
                        ),
                        BillingJob.next_attempt_at <= ahora,
                    )
                    .order_by(BillingJob.next_attempt_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()

            if job is None:
                return False

            job.status = "processing"
            job.attempts += 1
            job.next_attempt_at = ahora + timedelta(minutes=2)

            order_id = job.order_id
            intento = job.attempts

    async with database.session_factory() as session:
        order = await session.get(Order, order_id)

        if order is None:
            logger.error(
                "Pedido inexistente para facturacion: %s",
                order_id,
            )
            return True

        datos = dict(order.snapshot)

    try:
        factura = await enviar_factura_async(
            str(order_id),
            datos["items"],
            datos["total_cents"],
        )

        async with database.session_factory() as session:
            async with session.begin():
                job = await session.get(BillingJob, order_id)
                if job is not None:
                    job.status = "issued"
                    job.invoice_id = factura["id"]
                    job.last_error = None
                    job.updated_at = utcnow()

        logger.info(
            "Factura emitida order_id=%s invoice_id=%s",
            order_id,
            factura["id"],
        )

    except Exception as exc:
        codigo = exc.status if isinstance(exc, BillingError) else 0

        permanente = 400 <= codigo < 500 and codigo not in (408, 429)
        espera = min(5 * (2 ** min(intento - 1, 6)), 300)

        async with database.session_factory() as session:
            async with session.begin():
                job = await session.get(BillingJob, order_id)
                if job is not None:
                    job.status = "failed" if permanente else "retry"
                    job.last_error = (
                        f"HTTP {codigo}: {type(exc).__name__}"
                    )[:500]
                    job.next_attempt_at = utcnow() + timedelta(
                        seconds=espera
                    )
                    job.updated_at = utcnow()

        logger.warning(
            "Facturacion fallida order_id=%s intento=%s HTTP=%s",
            order_id,
            intento,
            codigo,
        )

    return True


async def billing_loop(database):
    while True:
        try:
            encontrado = await procesar_factura(database)
            await asyncio.sleep(0.5 if encontrado else 3)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Error en billing_loop: %s",
                type(exc).__name__,
            )
            await asyncio.sleep(5)
