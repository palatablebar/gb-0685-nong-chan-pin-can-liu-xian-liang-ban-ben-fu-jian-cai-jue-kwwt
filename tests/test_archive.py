import csv,io,json,time
from copy import deepcopy
from app import store
from app.modules.m7_archive.export_out import bundle,checksum,signed_payload
from app.workflow import load,run
from app.errors import DomainError
import pytest

def test_export_rows(state):
    rows=list(csv.reader(io.StringIO(bundle(state).lstrip('﻿'))));assert rows[0][0]=='记录类型' and rows[1][0]=='运行清单'
def test_export_quarantine(state):
    assert bundle(state).count('隔离')==len(state['quarantine'])
def test_checksum_stable(state):
    assert checksum(state)==state['archive']['content_sha256'] and len(checksum(state))==64
def test_archive_ready(state):
    assert state['archive']['ready'] is True
def test_idempotent_store(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    a=store.save(state['run_id'],state);b=store.save(state['run_id'],state)
    assert a['run_id']==b['run_id'] and len(store.history())==1
def test_stale_review(state,tmp_path,monkeypatch):
    # TRAP-26
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'));store.save(state['run_id'],state)
    assert store.review(state['run_id'],1,'通过')['review_version']==2
    with pytest.raises(DomainError) as e:store.review(state['run_id'],1,'退回')
    assert e.value.status==409
def test_persistent_new_connection(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'));store.save(state['run_id'],state)
    assert store.get(state['run_id'])['calculations']==state['calculations']

# ---- 稳定校验值与运行时刻分离 ----

def test_checksum_ignores_elapsed_and_generated_at(raw):
    first=run(raw,{});time.sleep(0.005);second=run(raw,{})
    assert first['archive']['content_sha256']==second['archive']['content_sha256']
    assert first['manifest']['runtime']['generated_at']!=second['manifest']['runtime']['generated_at']
    changed=deepcopy(first)
    changed['manifest']['runtime']['elapsed_ms']=99999
    changed['manifest']['runtime']['generated_at']='1999-01-01T00:00:00+00:00'
    assert checksum(changed)==checksum(first)

def test_checksum_covers_business_quarantine_and_reconcile(state):
    base=checksum(state)
    tampered=deepcopy(state);tampered['calculations'][0]['code']='PASS' if tampered['calculations'][0]['code']!='PASS' else 'FAIL'
    assert checksum(tampered)!=base
    quarantined=deepcopy(state)
    original=quarantined['quarantine'][0]['code']
    quarantined['quarantine'][0]['code']='MISSING' if original!='MISSING' else 'WIDTH'
    assert checksum(quarantined)!=base
    reconciled=deepcopy(state);reconciled['reconcile']['input']+=1
    assert checksum(reconciled)!=base

def test_signed_payload_excludes_runtime(state):
    payload=signed_payload(state)
    assert set(payload)=={'manifest','run_id','reconcile','calculations','quarantine'}
    assert 'elapsed_ms' not in json.dumps(payload,ensure_ascii=False)
    assert 'generated_at' not in json.dumps(payload,ensure_ascii=False)
    assert payload['manifest']['source_sha256'] and payload['manifest']['rule_version']

def test_manifest_split_structure(state):
    manifest=state['manifest']
    assert set(manifest)=={'signed','runtime'}
    assert set(manifest['signed'])=={'source_sha256','rule_version','parameters','timezone'}
    assert set(manifest['runtime'])=={'elapsed_ms','generated_at'}

# ---- 封存拦截与证据保护 ----

def test_seal_balanced(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'));store.save(state['run_id'],state)
    sealed=store.seal(state['run_id'])
    assert sealed['sealed'] is True and sealed['sealed_at']
    again=store.seal(state['run_id'])
    assert again['sealed'] is True

def _unbalanced(state):
    broken=deepcopy(state)
    broken['reconcile']['balanced']=False
    broken['reconcile']['unbalanced_batches']=['B002','*总账*']
    broken['run_id']='UNBAL-RUN'
    return broken

def test_seal_blocked_when_unbalanced(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    broken=_unbalanced(state);store.save(broken['run_id'],broken)
    with pytest.raises(DomainError) as e:store.seal(broken['run_id'])
    assert e.value.code=='UNBALANCED' and 'B002' in e.value.message
    assert store.get(broken['run_id'])['sealed'] is False

def test_tampered_evidence_rejected_keeps_old(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    rid=state['run_id'];store.save(rid,state);store.seal(rid)
    tampered=deepcopy(state)
    tampered['calculations'][0]['code']='PASS' if tampered['calculations'][0]['code']!='PASS' else 'FAIL'
    tampered['archive']['content_sha256']=checksum(tampered)
    with pytest.raises(DomainError) as e:store.save(rid,tampered)
    assert e.value.code=='EVIDENCE_CHANGED' and e.value.status==409
    kept=store.get(rid)
    assert kept['calculations'][0]['code']==state['calculations'][0]['code']
    assert kept['sealed'] is True

def test_rerun_same_source_keeps_confirmed_evidence(raw,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    first=run(raw,{});store.save(first['run_id'],first);store.seal(first['run_id'])
    second=run(raw,{})
    saved=store.save(second['run_id'],second)
    assert saved['archive']['content_sha256']==first['archive']['content_sha256']
    assert store.get(first['run_id'])['sealed'] is True

def test_reconcile_reports_unbalanced_batches():
    clean=run(load('clean.csv'),{})
    assert clean['reconcile']['balanced'] is True
    assert clean['reconcile']['unbalanced_batches']==[]
    broken=deepcopy(clean);broken['input_count']+=1
    from app.modules.m6_reconcile.compare import balance
    result=balance(broken)
    assert result['balanced'] is False and '*总账*' in result['unbalanced_batches']
