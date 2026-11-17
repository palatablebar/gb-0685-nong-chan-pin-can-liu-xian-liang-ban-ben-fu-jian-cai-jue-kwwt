import sqlite3,json,os
from pathlib import Path
from app.errors import DomainError

def connection():
    path=Path(os.environ.get('DB_PATH','data/records.db'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核")')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    # 封存登记：已封存批次的证据内容校验值与封存时刻，旧库平滑补列。
    existing={r['name'] for r in db.execute('PRAGMA table_info(runs)').fetchall()}
    if 'sealed' not in existing:db.execute("ALTER TABLE runs ADD COLUMN sealed INTEGER NOT NULL DEFAULT 0")
    if 'sealed_at' not in existing:db.execute("ALTER TABLE runs ADD COLUMN sealed_at TEXT")
    if 'content_sha256' not in existing:db.execute("ALTER TABLE runs ADD COLUMN content_sha256 TEXT")
    return db

def _content_checksum(body):
    archive=body.get('archive',{})
    return archive.get('content_sha256') or archive.get('sha256')

def save(run_id, body):
    checksum_value=_content_checksum(body)
    with connection() as db:
        existing=db.execute('SELECT body,sealed,content_sha256 FROM runs WHERE id=?',(run_id,)).fetchone()
        if existing is not None:
            # 同一来源重跑不得改换已确认证据：校验值不一致说明业务内容被改动，拒绝写入。
            if existing['sealed'] and checksum_value and existing['content_sha256'] and checksum_value!=existing['content_sha256']:
                raise DomainError('EVIDENCE_CHANGED','证据内容校验值与已封存版本不一致，禁止覆盖已确认证据',409)
            if checksum_value and existing['content_sha256'] and checksum_value!=existing['content_sha256']:
                raise DomainError('EVIDENCE_CHANGED','同批次证据内容校验值不一致，禁止覆盖既有证据',409)
        else:
            db.execute('INSERT INTO runs(id,body,content_sha256) VALUES (?,?,?)',(run_id,json.dumps(body,ensure_ascii=False),checksum_value))
        db.execute("INSERT INTO meta(key,value) VALUES ('latest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(run_id,))
    return get(run_id)

def get(run_id):
    with connection() as db:r=db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not r:raise DomainError('NOT_FOUND','批次不存在',404)
    body=json.loads(r['body']);body.update(run_id=r['id'],review_version=r['version'],decision=r['decision'],
        sealed=bool(r['sealed']),sealed_at=r['sealed_at'])
    return body

def history():
    with connection() as db:rows=db.execute("SELECT id,version,decision,sealed FROM runs ORDER BY CASE WHEN id=(SELECT value FROM meta WHERE key='latest') THEN 0 ELSE 1 END,rowid DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

def review(run_id, version, decision):
    if decision not in ('通过','退回'):raise DomainError('DECISION','复核状态无效')
    with connection() as db:
        cur=db.execute('UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?',(decision,run_id,version))
        if cur.rowcount!=1:
            if not db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():raise DomainError('NOT_FOUND','批次不存在',404)
            raise DomainError('STALE','复核版本已更新，请刷新',409)
    return get(run_id)

def seal(run_id):
    """封存证据。前置对账校验不通过或任何失败都不改动既有记录，旧版证据原样保留。"""
    from datetime import datetime,timezone
    with connection() as db:
        r=db.execute('SELECT body,sealed,content_sha256 FROM runs WHERE id=?',(run_id,)).fetchone()
        if not r:raise DomainError('NOT_FOUND','批次不存在',404)
        body=json.loads(r['body'])
        reconcile=body.get('reconcile',{})
        if not reconcile.get('balanced'):
            batches='、'.join(reconcile.get('unbalanced_batches',[])) or '未识别批次'
            raise DomainError('UNBALANCED','对账未平，批次 %s 账目不符，已拦截封存'%batches)
        checksum_value=_content_checksum(body)
        if r['sealed']:
            # 幂等封存：已封存且校验值一致直接返回，不生成新记录。
            if checksum_value and r['content_sha256'] and checksum_value!=r['content_sha256']:
                raise DomainError('EVIDENCE_CHANGED','证据内容校验值与已封存版本不一致，封存中止',409)
            return get(run_id)
        sealed_at=datetime.now(timezone.utc).isoformat()
        cur=db.execute('UPDATE runs SET sealed=1,sealed_at=?,content_sha256=? WHERE id=? AND sealed=0',
                       (sealed_at,checksum_value,run_id))
        if cur.rowcount!=1:raise DomainError('SEAL_CONFLICT','封存冲突，旧版证据已保留',409)
    return get(run_id)
