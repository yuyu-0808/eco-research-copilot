"""SQLite 统一存储层：指标库 / 项目元信息 / 系统配置。

按架构决策，checkpoint 的中间状态（Agent 阶段输出 / 信源素材 / 草稿）继续保留
JSON 文件，SQLite 只存轻量元数据与指标，二者通过 project_id 关联映射。

并发：后台执行线程（APScheduler 线程池）与 API 线程都会访问，采用 WAL 模式 +
每操作独立连接，支持并发读写；写操作用模块级锁串行化。
"""

import os
import sqlite3
import threading
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_ROOT, "data")
DB_PATH = os.path.join(_DATA_DIR, "app.db")

_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    framework_key TEXT NOT NULL,
    metric TEXT NOT NULL,
    metric_label TEXT,
    value TEXT,
    value_norm REAL,
    unit TEXT,
    period TEXT,
    year INTEGER,
    source_title TEXT,
    source_url TEXT,
    source_tier TEXT,
    publisher TEXT,
    report_id TEXT,
    saved_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_metrics_dedup
    ON metrics(framework_key, metric, year, value_norm);
CREATE INDEX IF NOT EXISTS idx_metrics_fw ON metrics(framework_key);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    topic TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    has_result INTEGER DEFAULT 0,
    has_docx INTEGER DEFAULT 0,
    n_charts INTEGER DEFAULT 0,
    n_tables INTEGER DEFAULT 0,
    checkpoint_path TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
"""


def _ensure_init():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        conn = _connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True
        _migrate_metrics_json()


def _migrate_metrics_json():
    """一次性迁移：把旧的 data/metrics_library/*.json 指标搬进 SQLite。"""
    import json
    legacy_dir = os.path.join(_DATA_DIR, "metrics_library")
    if not os.path.isdir(legacy_dir):
        return
    conn = _connect()
    try:
        for fn in os.listdir(legacy_dir):
            if not fn.endswith(".json"):
                continue
            fw = fn[:-5]
            try:
                with open(os.path.join(legacy_dir, fn), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, list):
                continue
            _insert_metrics(conn, fw, data, "")
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 指标库
# ----------------------------------------------------------------------
def metrics_insert(framework_key: str, entries: list, report_id: str = "") -> int:
    """插入指标条目（按 行业+指标+年份+归一化值 去重），返回新增条数。"""
    if not framework_key or framework_key == "generic" or not entries:
        return 0
    _ensure_init()
    conn = _connect()
    try:
        added = _insert_metrics(conn, framework_key, entries, report_id)
        conn.commit()
        return added
    finally:
        conn.close()


def _insert_metrics(conn, framework_key: str, entries: list, report_id: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    added = 0
    for en in entries:
        vn = en.get("value_norm")
        vn_r = round(vn, 4) if isinstance(vn, (int, float)) else None
        cur = conn.execute(
            """INSERT OR IGNORE INTO metrics
               (framework_key, metric, metric_label, value, value_norm, unit, period, year,
                source_title, source_url, source_tier, publisher, report_id, saved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                framework_key,
                en.get("metric"),
                en.get("metric_label"),
                en.get("value"),
                vn_r,
                en.get("unit"),
                en.get("period"),
                en.get("year"),
                en.get("source_title"),
                en.get("source_url"),
                en.get("source_tier"),
                en.get("publisher"),
                report_id,
                now,
            ),
        )
        added += cur.rowcount
    return added


def metrics_list(framework_key: str = None, metric: str = None, period: str = None) -> list:
    """检索指标（可按行业 / 指标 / 时间过滤）。"""
    _ensure_init()
    sql = "SELECT * FROM metrics WHERE 1=1"
    args = []
    if framework_key:
        sql += " AND framework_key=?"
        args.append(framework_key)
    if metric:
        sql += " AND metric=?"
        args.append(metric)
    if period:
        sql += " AND period=?"
        args.append(period)
    sql += " ORDER BY saved_at DESC, id DESC"
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def metrics_framework_keys() -> list:
    """返回有数据的行业 key 列表。"""
    _ensure_init()
    conn = _connect()
    try:
        return [r[0] for r in conn.execute("SELECT DISTINCT framework_key FROM metrics ORDER BY framework_key")]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 项目元信息
# ----------------------------------------------------------------------
def project_upsert(project_id: str, **fields) -> None:
    """写入 / 更新项目元信息（id/标题/状态/图表数等，与磁盘 JSON 关联）。"""
    _ensure_init()
    now = datetime.now().isoformat(timespec="seconds")
    data = {
        "id": project_id,
        "topic": fields.get("topic", ""),
        "status": fields.get("status", ""),
        "has_result": int(bool(fields.get("has_result", False))),
        "has_docx": int(bool(fields.get("has_docx", False))),
        "n_charts": int(fields.get("n_charts", 0) or 0),
        "n_tables": int(fields.get("n_tables", 0) or 0),
        "checkpoint_path": fields.get("checkpoint_path", ""),
        "updated_at": now,
    }
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO projects
               (id, topic, status, created_at, updated_at, has_result, has_docx, n_charts, n_tables, checkpoint_path)
               VALUES (:id, :topic, :status, :updated_at, :updated_at, :has_result, :has_docx, :n_charts, :n_tables, :checkpoint_path)
               ON CONFLICT(id) DO UPDATE SET
                 topic=excluded.topic, status=excluded.status, updated_at=excluded.updated_at,
                 has_result=excluded.has_result, has_docx=excluded.has_docx,
                 n_charts=excluded.n_charts, n_tables=excluded.n_tables, checkpoint_path=excluded.checkpoint_path""",
            data,
        )
        conn.commit()
    finally:
        conn.close()


def project_get(project_id: str):
    """读取单个项目元信息。"""
    _ensure_init()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def projects_list() -> list:
    """读取全部项目元信息（供统计看板使用）。"""
    _ensure_init()
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY created_at DESC")]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 系统配置
# ----------------------------------------------------------------------
def config_get(key: str, default=None):
    _ensure_init()
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    finally:
        conn.close()


def config_set(key: str, value: str) -> None:
    _ensure_init()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO config (key, value, updated_at) VALUES (?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, str(value), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
