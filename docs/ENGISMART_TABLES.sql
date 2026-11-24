-- Engismart's own tables: tbl_engismart_image (one row per picture found in a document) and tbl_engismart_chat_turn (one row per
-- answered question, with its answer and sources: the conversation list and history of the UI).
-- Run once per environment on the PLATFORM database, BEFORE the first start (the platform does not create tables by itself:
-- the create_all hook at the end of models/orm_models.py belongs to a FastAPI() that is never served).
-- The class is EngismartImage in models/orm_models.py (added by tools/assemble.py); the code is controller/engismart/ingestion/images/catalog.py.

-- MySQL 8
CREATE TABLE IF NOT EXISTS tbl_engismart_image (
    id            VARCHAR(36)  NOT NULL,
    doc_id        VARCHAR(64)  NOT NULL,
    `position`    INT          NOT NULL DEFAULT 0,
    sha256        VARCHAR(64)  NOT NULL,
    location      JSON         NOT NULL,
    context       TEXT         NOT NULL,
    width         INT          NOT NULL DEFAULT 0,
    height        INT          NOT NULL DEFAULT 0,
    status        VARCHAR(16)  NOT NULL DEFAULT 'waiting',
    reason        VARCHAR(160) NOT NULL DEFAULT '',
    manual        TINYINT(1)   NOT NULL DEFAULT 0,
    description   TEXT         NOT NULL,
    input_tokens  INT          NOT NULL DEFAULT 0,
    output_tokens INT          NOT NULL DEFAULT 0,
    described_at  DATETIME     NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_tbl_engismart_image_doc_id (doc_id),
    KEY ix_tbl_engismart_image_sha256 (sha256),
    KEY ix_tbl_engismart_image_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PostgreSQL (the `aws` environment): the same table
-- CREATE TABLE IF NOT EXISTS tbl_engismart_image (
--     id VARCHAR(36) PRIMARY KEY, doc_id VARCHAR(64) NOT NULL, position INTEGER NOT NULL DEFAULT 0, sha256 VARCHAR(64) NOT NULL,
--     location JSON NOT NULL, context TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
--     status VARCHAR(16) NOT NULL DEFAULT 'waiting', reason VARCHAR(160) NOT NULL DEFAULT '', manual BOOLEAN NOT NULL DEFAULT FALSE,
--     description TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
--     described_at TIMESTAMPTZ NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
-- CREATE INDEX ix_tbl_engismart_image_doc_id ON tbl_engismart_image (doc_id);
-- CREATE INDEX ix_tbl_engismart_image_sha256 ON tbl_engismart_image (sha256);
-- CREATE INDEX ix_tbl_engismart_image_status ON tbl_engismart_image (status);

-- MySQL 8
CREATE TABLE IF NOT EXISTS tbl_engismart_chat_turn (
    id          INT          NOT NULL AUTO_INCREMENT,
    user_id     INT          NOT NULL,
    session_id  VARCHAR(128) NOT NULL,
    turn_no     INT          NOT NULL,
    question    TEXT         NOT NULL,
    answer      TEXT         NOT NULL,
    sources     TEXT         NOT NULL,
    mode        VARCHAR(32)  NOT NULL DEFAULT '',
    created_on  DATETIME     NOT NULL,
    PRIMARY KEY (id),
    KEY ix_tbl_engismart_chat_turn_user_id (user_id),
    KEY ix_tbl_engismart_chat_turn_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PostgreSQL (the `aws` environment): the same table
-- CREATE TABLE IF NOT EXISTS tbl_engismart_chat_turn (
--     id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, session_id VARCHAR(128) NOT NULL, turn_no INTEGER NOT NULL,
--     question TEXT NOT NULL, answer TEXT NOT NULL, sources TEXT NOT NULL, mode VARCHAR(32) NOT NULL DEFAULT '',
--     created_on TIMESTAMP NOT NULL);
-- CREATE INDEX ix_tbl_engismart_chat_turn_user_id ON tbl_engismart_chat_turn (user_id);
-- CREATE INDEX ix_tbl_engismart_chat_turn_session_id ON tbl_engismart_chat_turn (session_id);

-- Chat memory is NOT in this file: langgraph-checkpoint-mysql creates its own tables (checkpoints, checkpoint_blobs, checkpoint_writes,
-- checkpoint_migrations) the first time the chat is used. The database user therefore needs CREATE TABLE rights, or DevOps runs the
-- library's setup once from any machine that can reach the database (needs the project's Python environment):
--   python -c "import pymysql; from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver; PyMySQLSaver(pymysql.connect(host='HOST', user='USER', password='PASSWORD', database='DATABASE', autocommit=True)).setup()"
