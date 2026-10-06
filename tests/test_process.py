from fastapi.testclient import TestClient
from backend import app as service
import pytest

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'DATA',tmp_path)
    return TestClient(service.app)

def request(**changes):
    return dict(name='Анна',email='anna@example.com',message='Хочу заказать столы',idempotency_key='unique-request',simulate_failure=True,**changes)

def test_retry_does_not_duplicate_business_effects(client):
    first=client.post('/api/runs',json=request()).json()
    assert first['state']=='failed'
    assert first['result']['ticket']
    assert 'notification' not in first['result']
    second=client.post(f"/api/runs/{first['id']}/retry").json()
    third=client.post(f"/api/runs/{first['id']}/retry").json()
    assert second['state']=='completed'
    assert second==third
    assert second['result']['ticket']==first['result']['ticket']
    with service.db() as conn:
        assert conn.execute('SELECT count(*) FROM tickets').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM notifications').fetchone()[0]==1

def test_idempotency_and_conflicting_payload(client):
    a=client.post('/api/runs',json=request()).json()
    b=client.post('/api/runs',json=request()).json()
    assert a==b
    payload=request();payload['message']='Совсем другая заявка'
    assert client.post('/api/runs',json=payload).status_code==409

def test_invalid_contact_has_no_ticket(client):
    payload=request();payload['email']='bad-mail'
    a=client.post('/api/runs',json=payload).json()
    assert a['state']=='failed'
    assert 'ticket' not in a['result']
    assert client.post('/api/runs/missing/retry').status_code==404
