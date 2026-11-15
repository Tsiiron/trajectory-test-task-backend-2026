from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, ForeignKey, MetaData, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr

naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))


class AbstractCustomer(db.Model):
    """
    Теперь каждая сущность
    отдельная строка с индексами по crm_id, login и name.

    "send_methods": [
        {
            "type": str (mail,sms,wtsp),
            "value": str,
            "desc": str,
        }
    ]
    """
    __tablename__ = "abstract_customer"
    id = Column(db.BigInteger(), nullable=False, primary_key=True)
    send_methods = Column(JSONB)
    created_at = Column(db.DateTime, server_default=func.now())
    updated_at = Column(db.DateTime, onupdate=func.now())

    amo_customers = db.relationship("AmoCustomer", back_populates="abstract_customer", passive_deletes=True)
    amo_leads = db.relationship("AmoLead", back_populates="abstract_customer", passive_deletes=True)
    amo_contacts = db.relationship("AmoContact", back_populates="abstract_customer", passive_deletes=True)
    amo_companies = db.relationship("AmoCompany", back_populates="abstract_customer", passive_deletes=True)


class AmoEntityMixin:
    """
    Общие поля сущности CRM.

    crm_id      — id в amoCRM;
    name        — название (по нему ищут другие части системы);
    general     — JSON в прежнем формате ("general" из старых массивов);
    api_value   — ответ API как есть;
    synced_at   — когда сущность последний раз видели в выгрузке (по нему чистка).
    """
    id = Column(db.BigInteger(), nullable=False, primary_key=True)
    crm_id = Column(db.BigInteger(), nullable=False)
    name = Column(db.Text, index=True)
    general = Column(JSONB)
    api_value = Column(JSONB)
    synced_at = Column(db.DateTime(timezone=True))

    @declared_attr
    def abstract_customer_id(cls):
        return Column(db.BigInteger(), ForeignKey("abstract_customer.id", ondelete="CASCADE"),
                      nullable=False, index=True)


class AmoCustomer(AmoEntityMixin, db.Model):
    __tablename__ = "amo_customer"
    __table_args__ = (UniqueConstraint("crm_id"),)
    login = Column(db.Text, index=True)
    abstract_customer = db.relationship("AbstractCustomer", back_populates="amo_customers")


class AmoLead(AmoEntityMixin, db.Model):
    __tablename__ = "amo_lead"
    __table_args__ = (UniqueConstraint("crm_id"),)
    login = Column(db.Text, index=True)
    abstract_customer = db.relationship("AbstractCustomer", back_populates="amo_leads")


class AmoContact(AmoEntityMixin, db.Model):
    __tablename__ = "amo_contact"
    __table_args__ = (UniqueConstraint("abstract_customer_id", "crm_id"),)
    abstract_customer = db.relationship("AbstractCustomer", back_populates="amo_contacts")


class AmoCompany(AmoEntityMixin, db.Model):
    __tablename__ = "amo_company"
    __table_args__ = (UniqueConstraint("abstract_customer_id", "crm_id"),)
    abstract_customer = db.relationship("AbstractCustomer", back_populates="amo_companies")
