# -*- coding: utf-8 -*-
"""SQLite 存储层：建表、查询、写审计。表结构与 v1 完全一致（升级不丢数据）。"""
from __future__ import annotations

import json
import sqlite3
import threading

from . import conf as C
from .util import now

_db_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents(
  agent_id TEXT PRIMARY KEY, token TEXT, fingerprint TEXT, host TEXT, version TEXT,
  created_at REAL, last_seen REAL, load1 TEXT, disk TEXT, mem TEXT, extra TEXT);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, batch_id TEXT, agent_id TEXT, task TEXT, state TEXT,
  result TEXT, log TEXT, created_at REAL, started_at REAL, finished_at REAL);
CREATE TABLE IF NOT EXISTS enrollments(
  id TEXT PRIMARY KEY, agent_id TEXT, fingerprint TEXT, host TEXT, challenge TEXT,
  secret_ok INTEGER DEFAULT 0, status TEXT, token TEXT, created_at REAL, decided_at REAL);
CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, agent_id TEXT,
  action TEXT, detail TEXT, task_id TEXT);
CREATE TABLE IF NOT EXISTS releases(
  version TEXT PRIMARY KEY, filename TEXT, sha256 TEXT, sig TEXT, notes TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS blocked(
  agent_id TEXT PRIMARY KEY, reason TEXT, at REAL, wipe INTEGER DEFAULT 1, wipe_done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def db():
    C.ensure_home()
    conn = sqlite3.connect(str(C.DBPATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


def init():
    with _db_lock, db() as conn:
        conn.executescript(SCHEMA)


def q(sql, args=(), one=False):
    """查询：one=True 返回一条 dict（或 None），否则返回 list[dict]。"""
    with _db_lock, db() as conn:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


def x(sql, args=()):
    """执行写操作。"""
    with _db_lock, db() as conn:
        conn.execute(sql, args)
        conn.commit()


def audit(actor, action, agent_id='', detail='', task_id=''):
    """记一条审计（谁、何时、对谁、做了什么）。"""
    x('INSERT INTO audit(ts,actor,agent_id,action,detail,task_id) VALUES(?,?,?,?,?,?)',
      (now(), actor, agent_id, action, str(detail)[:2000], task_id))


def set_meta(k, v):
    x("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def get_meta(k):
    row = q('SELECT v FROM meta WHERE k=?', (k,), one=True)
    return row['v'] if row else None


def gc_nonces(max_age=900):
    """清掉过期 nonce（防重放用，超过时间窗就没必要留了）。"""
    x('DELETE FROM nonces WHERE ts < ?', (now() - max_age,))


def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
