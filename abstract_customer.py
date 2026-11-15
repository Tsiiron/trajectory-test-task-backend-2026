import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from amocrm import Customer, Lead
from models import (AbstractCustomer, AmoCompany, AmoContact, AmoCustomer,
                    AmoLead, db)

logger = logging.getLogger(__name__)

DELETE_MARK = 'удалить'



def get_customer_json(customer: Customer) -> dict:
    return {
        'general': {
            'id': customer.id,
            'login': customer.get_field('Логин'),
            'billing_type': customer.get_field('Вид оплаты'),
            'is_robot': bool(customer.get_field('Робот')),
            'is_nds': bool(customer.get_field('Оплата с НДС')),
            'system': customer.get_field('Система'),
            'host': customer.get_field('Хост'),
            'name': customer.name,
        },
        'api_value': customer.as_dict()
    }


def get_lead_json(lead: Lead) -> dict:
    return {
        'general': {
            'id': lead.id,
            'login': lead.get_field('Логин'),
            'name': lead.name,
        },
        'api_value': lead.as_dict()
    }



def _records_by_crm_id(model, crm_ids: Iterable[int]) -> Dict[int, int]:
    rows = db.session.execute(
        select(model.crm_id, model.abstract_customer_id).where(model.crm_id.in_(list(crm_ids))))
    return {crm_id: abstract_id for crm_id, abstract_id in rows}


def _records_by_login(model, logins: Iterable[str]) -> Dict[str, Set[int]]:
    result: Dict[str, Set[int]] = defaultdict(set)
    rows = db.session.execute(
        select(model.login, model.abstract_customer_id).where(model.login.in_(list(logins))).distinct())
    for login, abstract_id in rows:
        result[login].add(abstract_id)
    return result


def _single(abstract_ids: Set[int], login: str) -> Optional[int]:
    if len(abstract_ids) > 1:
        logger.warning(f"Логин {login} найден у нескольких абстрактных покупателей")
        return None
    return next(iter(abstract_ids), None)


def _dedupe(entities: Iterable) -> list:
    return list({e.id: e for e in entities}.values())


def _create_records(count: int) -> List[int]:
    records = [AbstractCustomer() for _ in range(count)]
    db.session.add_all(records)
    db.session.flush()
    return [r.id for r in records]


def _fill_new_records(targets: Dict[int, Optional[int]]) -> None:
    missing = [key for key, value in targets.items() if value is None]
    if missing:
        for key, new_id in zip(missing, _create_records(len(missing))):
            targets[key] = new_id


def _upsert_entities(model, rows: List[dict]) -> None:
    stmt = pg_insert(model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=['crm_id'],
        set_={col: stmt.excluded[col] for col in ('login', 'name', 'general', 'api_value', 'synced_at')},
    )
    db.session.execute(stmt)


def _upsert_links(model, links: Dict[Tuple[int, int], dict], synced_at: datetime) -> None:
    if not links:
        return
    rows = [{
        'abstract_customer_id': abstract_id,
        'crm_id': crm_id,
        'name': embedded.get('name'),
        'general': {'id': crm_id},
        'api_value': embedded,
        'synced_at': synced_at,
    } for (abstract_id, crm_id), embedded in links.items()]
    stmt = pg_insert(model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=['abstract_customer_id', 'crm_id'],
        set_={'synced_at': stmt.excluded.synced_at},
    )
    db.session.execute(stmt)


def sync_customers(customers: List[Customer], synced_at: datetime) -> None:
    customers = _dedupe(c for c in customers if c.get_field('Логин'))
    if not customers:
        return

    by_id = _records_by_crm_id(AmoCustomer, (c.id for c in customers))
    by_login = _records_by_login(AmoLead, {c.get_field('Логин') for c in customers})

    targets: Dict[int, Optional[int]] = {}
    for customer in customers:
        login = customer.get_field('Логин')
        target = by_id.get(customer.id)
        if target is None:
            target = _single(by_login.get(login, set()), login)
        targets[customer.id] = target
    _fill_new_records(targets)

    rows, contacts, companies = [], {}, {}
    for customer in customers:
        general = get_customer_json(customer)
        abstract_id = targets[customer.id]
        rows.append({
            'crm_id': customer.id,
            'abstract_customer_id': abstract_id,
            'login': general['general']['login'],
            'name': customer.name,
            'general': general['general'],
            'api_value': general['api_value'],
            'synced_at': synced_at,
        })
        for contact in customer.contacts:
            contacts[(abstract_id, contact['id'])] = contact
        for company in customer.companies:
            companies[(abstract_id, company['id'])] = company

    _upsert_entities(AmoCustomer, rows)
    _upsert_links(AmoContact, contacts, synced_at)
    _upsert_links(AmoCompany, companies, synced_at)


def merge_records(keep_id: int, drop_id: int) -> None:
    session = db.session
    no_sync = {'synchronize_session': False}
    for model in (AmoCustomer, AmoLead):
        session.execute(update(model).where(model.abstract_customer_id == drop_id)
                        .values(abstract_customer_id=keep_id), execution_options=no_sync)
    for model in (AmoContact, AmoCompany):
        already = select(model.crm_id).where(model.abstract_customer_id == keep_id)
        session.execute(update(model).where(model.abstract_customer_id == drop_id, model.crm_id.not_in(already))
                        .values(abstract_customer_id=keep_id), execution_options=no_sync)

    keep, drop = session.get(AbstractCustomer, keep_id), session.get(AbstractCustomer, drop_id)
    merged = list(keep.send_methods or [])
    merged += [m for m in (drop.send_methods or []) if m not in merged]
    if merged:
        keep.send_methods = merged
    session.delete(drop)
    session.flush()


def sync_leads(leads: List[Lead], synced_at: datetime) -> None:
    leads = _dedupe(leads)
    if not leads:
        return

    by_id = _records_by_crm_id(AmoLead, (l.id for l in leads))
    by_login = _records_by_login(AmoCustomer, {l.get_field('Логин') for l in leads if l.get_field('Логин')})

    merged_into: Dict[int, int] = {}

    def resolve(abstract_id: int) -> int:
        while abstract_id in merged_into:
            abstract_id = merged_into[abstract_id]
        return abstract_id

    targets: Dict[int, Optional[int]] = {}
    for lead in leads:
        login = lead.get_field('Логин')
        by_lead = resolve(by_id[lead.id]) if lead.id in by_id else None
        by_customer = None
        if login:
            by_customer = _single({resolve(i) for i in by_login.get(login, set())}, login)

        if by_lead is not None and by_customer is not None and by_lead != by_customer:
            merge_records(keep_id=by_lead, drop_id=by_customer)
            merged_into[by_customer] = by_lead
            by_customer = by_lead
        targets[lead.id] = by_lead if by_lead is not None else by_customer

    for key, value in targets.items():
        if value is not None:
            targets[key] = resolve(value)
    _fill_new_records(targets)

    rows, contacts = [], {}
    for lead in leads:
        general = get_lead_json(lead)
        abstract_id = targets[lead.id]
        rows.append({
            'crm_id': lead.id,
            'abstract_customer_id': abstract_id,
            'login': general['general']['login'],
            'name': lead.name,
            'general': general['general'],
            'api_value': general['api_value'],
            'synced_at': synced_at,
        })
        for contact in lead.contacts:
            contacts[(abstract_id, contact['id'])] = contact

    _upsert_entities(AmoLead, rows)
    _upsert_links(AmoContact, contacts, synced_at)


def delete_stale(run_started: datetime) -> None:
    session = db.session
    for model in (AmoCustomer, AmoLead, AmoContact, AmoCompany):
        session.execute(delete(model).where(or_(
            model.synced_at.is_(None),
            model.synced_at < run_started,
            func.lower(model.name).like(f'%{DELETE_MARK}%'),
        )))
    has_customer = exists().where(AmoCustomer.abstract_customer_id == AbstractCustomer.id)
    has_lead = exists().where(AmoLead.abstract_customer_id == AbstractCustomer.id)
    session.execute(delete(AbstractCustomer).where(~has_customer, ~has_lead))
    session.commit()
