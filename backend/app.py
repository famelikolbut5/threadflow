"""A small executable workflow engine. Each completed node commits its output."""
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .web import serve_web

app = FastAPI(title='Threadflow')
DATA = Path(os.environ.get('DEMO_DATA', Path(__file__).resolve().parents[1] / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()
NODES = ['intake', 'validate', 'classify', 'ticket', 'notify']

def db():
    conn = sqlite3.connect(DATA / 'workflow.sqlite', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, idem TEXT UNIQUE, digest TEXT, payload TEXT, state TEXT, trace TEXT, result TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, run_id TEXT UNIQUE, payload TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS notifications(run_id TEXT UNIQUE, body TEXT)')
    return conn

class Request(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=5, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=100)
    simulate_failure: bool = False

def unpack(row):
    return {'id': row['id'], 'state': row['state'], 'trace': json.loads(row['trace']), 'result': json.loads(row['result'])}

def execute(conn, row, retry=False):
    payload = json.loads(row['payload'])
    trace = json.loads(row['trace'])
    result = json.loads(row['result'])
    done = {item['node'] for item in trace if item['status'] == 'completed'}
    for node in NODES:
        if node in done:
            continue
        stamp = datetime.now(timezone.utc).isoformat()
        error = None
        if node == 'validate' and ('@' not in payload['email'] or '.' not in payload['email'].split('@')[-1]):
            error = 'Укажите email с доменом: name@example.com'
        elif node == 'notify' and payload['simulate_failure'] and not retry:
            error = 'Тестовый сбой канала уведомлений. Повторите этот шаг.'
        else:
            if node == 'classify':
                # Explicit rule classifier, not a language model.
                result['category'] = 'Продажи' if any(w in payload['message'].lower() for w in ['куп', 'цен', 'заказ', 'quote']) else 'Поддержка'
            elif node == 'ticket':
                ticket = 'TF-' + row['id'][:8].upper()
                conn.execute('INSERT OR IGNORE INTO tickets VALUES(?,?,?)', (ticket, row['id'], json.dumps(payload)))
                result['ticket'] = ticket
            elif node == 'notify':
                body = f"Заявка {result['ticket']} от {payload['name']}: {result['category']}"
                conn.execute('INSERT OR IGNORE INTO notifications VALUES(?,?)', (row['id'], body))
                result['notification'] = body
        trace.append({'node': node, 'status': 'failed' if error else 'completed', 'at': stamp, 'detail': error or {'intake':'Заявка принята','validate':'Контакты проверены','classify':result.get('category'), 'ticket':result.get('ticket'), 'notify':result.get('notification')}[node]})
        state = 'failed' if error else ('completed' if node == NODES[-1] else 'running')
        conn.execute('UPDATE runs SET state=?,trace=?,result=? WHERE id=?', (state, json.dumps(trace), json.dumps(result), row['id']))
        conn.commit()
        if error:
            break
    return unpack(conn.execute('SELECT * FROM runs WHERE id=?', (row['id'],)).fetchone())

@app.get('/api/runs')
def runs():
    with db() as conn:
        return [unpack(r) for r in conn.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 30')]

@app.post('/api/runs')
def run(request: Request):
    payload = request.model_dump(exclude={'idempotency_key'})
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with LOCK, db() as conn:
        row = conn.execute('SELECT * FROM runs WHERE idem=?', (request.idempotency_key,)).fetchone()
        if row:
            if row['digest'] != digest:
                raise HTTPException(409, 'Этот ключ уже использован с другой заявкой')
            return unpack(row)
        rid = uuid4().hex
        conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?)', (rid, request.idempotency_key, digest, json.dumps(payload), 'running', '[]', '{}'))
        conn.commit()
        return execute(conn, conn.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone())

@app.post('/api/runs/{rid}/retry')
def retry(rid: str):
    with LOCK, db() as conn:
        row = conn.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Запуск не найден')
        return execute(conn, row, retry=True)

@app.get('/api/health')
def health():
    return {'status':'ok','notifications':'local outbox; external delivery not configured'}

serve_web(app)
