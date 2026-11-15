-- Переход со старой схемы (четыре JSONB-массива в abstract_customer) на отдельные таблицы сущностей.
BEGIN;

CREATE TABLE amo_customer (
    id BIGSERIAL NOT NULL,
    crm_id BIGINT NOT NULL,
    name TEXT,
    general JSONB,
    api_value JSONB,
    synced_at TIMESTAMPTZ,
    abstract_customer_id BIGINT NOT NULL,
    login TEXT,
    CONSTRAINT pk_amo_customer PRIMARY KEY (id),
    CONSTRAINT uq_amo_customer_crm_id UNIQUE (crm_id),
    CONSTRAINT fk_amo_customer_abstract_customer_id_abstract_customer
        FOREIGN KEY (abstract_customer_id) REFERENCES abstract_customer (id) ON DELETE CASCADE
);

CREATE TABLE amo_lead (
    id BIGSERIAL NOT NULL,
    crm_id BIGINT NOT NULL,
    name TEXT,
    general JSONB,
    api_value JSONB,
    synced_at TIMESTAMPTZ,
    abstract_customer_id BIGINT NOT NULL,
    login TEXT,
    CONSTRAINT pk_amo_lead PRIMARY KEY (id),
    CONSTRAINT uq_amo_lead_crm_id UNIQUE (crm_id),
    CONSTRAINT fk_amo_lead_abstract_customer_id_abstract_customer
        FOREIGN KEY (abstract_customer_id) REFERENCES abstract_customer (id) ON DELETE CASCADE
);

CREATE TABLE amo_contact (
    id BIGSERIAL NOT NULL,
    crm_id BIGINT NOT NULL,
    name TEXT,
    general JSONB,
    api_value JSONB,
    synced_at TIMESTAMPTZ,
    abstract_customer_id BIGINT NOT NULL,
    CONSTRAINT pk_amo_contact PRIMARY KEY (id),
    CONSTRAINT uq_amo_contact_abstract_customer_id UNIQUE (abstract_customer_id, crm_id),
    CONSTRAINT fk_amo_contact_abstract_customer_id_abstract_customer
        FOREIGN KEY (abstract_customer_id) REFERENCES abstract_customer (id) ON DELETE CASCADE
);

CREATE TABLE amo_company (
    id BIGSERIAL NOT NULL,
    crm_id BIGINT NOT NULL,
    name TEXT,
    general JSONB,
    api_value JSONB,
    synced_at TIMESTAMPTZ,
    abstract_customer_id BIGINT NOT NULL,
    CONSTRAINT pk_amo_company PRIMARY KEY (id),
    CONSTRAINT uq_amo_company_abstract_customer_id UNIQUE (abstract_customer_id, crm_id),
    CONSTRAINT fk_amo_company_abstract_customer_id_abstract_customer
        FOREIGN KEY (abstract_customer_id) REFERENCES abstract_customer (id) ON DELETE CASCADE
);

INSERT INTO amo_customer (crm_id, abstract_customer_id, login, name, general, api_value)
SELECT DISTINCT ON ((e->'general'->>'id')::bigint)
       (e->'general'->>'id')::bigint, ac.id, e->'general'->>'login', e->'general'->>'name', e->'general', e->'api_value'
FROM abstract_customer ac, jsonb_array_elements(CASE WHEN jsonb_typeof(ac.amo_customers) = 'array' THEN ac.amo_customers ELSE '[]' END) e
ORDER BY (e->'general'->>'id')::bigint, ac.id;

INSERT INTO amo_lead (crm_id, abstract_customer_id, login, name, general, api_value)
SELECT DISTINCT ON ((e->'general'->>'id')::bigint)
       (e->'general'->>'id')::bigint, ac.id, e->'general'->>'login', e->'general'->>'name', e->'general', e->'api_value'
FROM abstract_customer ac, jsonb_array_elements(CASE WHEN jsonb_typeof(ac.amo_leads) = 'array' THEN ac.amo_leads ELSE '[]' END) e
ORDER BY (e->'general'->>'id')::bigint, ac.id;

INSERT INTO amo_contact (crm_id, abstract_customer_id, name, general, api_value)
SELECT DISTINCT ON (ac.id, (e->'general'->>'id')::bigint)
       (e->'general'->>'id')::bigint, ac.id, e->'general'->>'name', e->'general', e->'api_value'
FROM abstract_customer ac, jsonb_array_elements(CASE WHEN jsonb_typeof(ac.amo_contacts) = 'array' THEN ac.amo_contacts ELSE '[]' END) e;

INSERT INTO amo_company (crm_id, abstract_customer_id, name, general, api_value)
SELECT DISTINCT ON (ac.id, (e->'general'->>'id')::bigint)
       (e->'general'->>'id')::bigint, ac.id, e->'general'->>'name', e->'general', e->'api_value'
FROM abstract_customer ac, jsonb_array_elements(CASE WHEN jsonb_typeof(ac.amo_companies) = 'array' THEN ac.amo_companies ELSE '[]' END) e;

CREATE INDEX ix_amo_customer_name ON amo_customer (name);
CREATE INDEX ix_amo_customer_abstract_customer_id ON amo_customer (abstract_customer_id);
CREATE INDEX ix_amo_customer_login ON amo_customer (login);
CREATE INDEX ix_amo_lead_name ON amo_lead (name);
CREATE INDEX ix_amo_lead_abstract_customer_id ON amo_lead (abstract_customer_id);
CREATE INDEX ix_amo_lead_login ON amo_lead (login);
CREATE INDEX ix_amo_contact_name ON amo_contact (name);
CREATE INDEX ix_amo_contact_abstract_customer_id ON amo_contact (abstract_customer_id);
CREATE INDEX ix_amo_company_name ON amo_company (name);
CREATE INDEX ix_amo_company_abstract_customer_id ON amo_company (abstract_customer_id);


COMMIT;
