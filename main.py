import logging
from datetime import datetime, timezone
from itertools import islice
from typing import Callable, Iterable, Iterator, List

from abstract_customer import delete_stale, sync_customers, sync_leads
from amocrm import COMPANIES, CONTACTS, Customer, Lead, amocrm_get
from models import db

logger = logging.getLogger(__name__)

BATCH_SIZE = 250
CUSTOMER_CLOSED_STATUS_ID = 111349
LEAD_CLOSED_STATUS_ID = 143


def _batches(items: Iterable, size: int) -> Iterator[list]:
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def _process(items: Iterable, handler: Callable[[List, datetime], None], run_started: datetime) -> bool:
    ok = True
    for batch in _batches(items, BATCH_SIZE):
        try:
            handler(batch, run_started)
            db.session.commit()
            continue
        except Exception:
            db.session.rollback()
            logger.exception("Пачка не сохранилась, повторяем по одной сущности")
        for entity in batch:
            try:
                handler([entity], run_started)
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception(f"{entity}")
                ok = False
    return ok


def collect_leads_customers(is_full=True):
    run_started = datetime.now(timezone.utc)
    try:
        customers = (c for c in amocrm_get(Customer, _with=f"{COMPANIES},{CONTACTS}")
                     if is_full or c.status_id != CUSTOMER_CLOSED_STATUS_ID)
        ok = _process(customers, sync_customers, run_started)
        logger.info(f"Покупатели собраны {is_full=}")

        leads = (l for l in amocrm_get(Lead, _with=CONTACTS)
                 if is_full or l.status_id != LEAD_CLOSED_STATUS_ID)
        ok = _process(leads, sync_leads, run_started) and ok
        logger.info(f"Сделки собраны {is_full=}")
    except Exception:
        db.session.rollback()
        logger.exception("Сбор прерван, чистка пропущена")
        raise

    if is_full is False:
        return
    if not ok:
        logger.error("Часть сущностей не сохранена, чистка пропущена")
        return
    logger.info("Чистка")
    delete_stale(run_started)
