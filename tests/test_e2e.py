from app.config import MODULES

def test_all_module_apis(client):
    for mod,_ in MODULES:assert client.get('/api/'+mod).status_code==200
def test_all_module_pages(client):
    for mod,_ in MODULES:assert client.get('/'+mod).status_code==200
def test_run_and_export(client):
    r=client.post('/api/runs',json={'sample':'dirty.csv'});assert r.status_code==200
    s=r.get_json();e=client.get('/api/archive/'+s['run_id']+'/export.csv');assert e.status_code==200 and '运行清单' in e.data.decode('utf-8-sig')
def test_idempotent_api(client):
    a=client.post('/api/runs',json={}).get_json();b=client.post('/api/runs',json={}).get_json()
    assert a['run_id']==b['run_id'] and len(client.get('/api/runs').get_json())==1
def test_bad_sample(client):
    r=client.post('/api/runs',json={'sample':'../x'});assert r.status_code==422 and r.get_json()['code']=='SAMPLE'
def test_missing_batch(client):
    assert client.get('/api/runs/absent').status_code==404
def test_bad_file(client):
    r=client.post('/api/runs',json={'csv':'wrong\n1\n'});assert r.status_code==422 and r.get_json()['code']=='HEADER'


def test_custom_source_is_visible_after_run(client):
    from app.workflow import load
    raw=load('clean.csv').decode('utf-8-sig');submitted=client.post('/api/runs',json={'csv':raw,'parameters':{}}).get_json()
    from app.config import MODULES
    page=client.get('/'+MODULES[0][0]);assert submitted['run_id'] in page.data.decode()

def test_reselect_existing_run_updates_visible_batch(client):
    a=client.post('/api/runs',json={'sample':'dirty.csv'}).get_json();b=client.post('/api/runs',json={'sample':'clean.csv'}).get_json();client.post('/api/runs',json={'sample':'dirty.csv'})
    assert client.get('/api/runs').get_json()[0]['id']==a['run_id'] and a['run_id']!=b['run_id']

def test_invalid_csv_type_rejected(client):
    assert client.post('/api/runs',json={'csv':123}).status_code==422

def test_seal_flow_and_idempotent(client):
    sid=client.post('/api/runs',json={'sample':'dirty.csv'}).get_json()['run_id']
    r=client.post('/api/runs/'+sid+'/seal');assert r.status_code==200 and r.get_json()['sealed'] is True
    again=client.post('/api/runs/'+sid+'/seal');assert again.status_code==200 and again.get_json()['sealed'] is True
    assert client.post('/api/runs/missing/seal').status_code==404

def test_unbalanced_seal_blocked_with_batch(client):
    import sqlite3,json,os
    sid=client.post('/api/runs',json={'sample':'dirty.csv'}).get_json()['run_id']
    db=sqlite3.connect(os.environ['DB_PATH']);row=db.execute('SELECT body FROM runs WHERE id=?',(sid,)).fetchone()
    body=json.loads(row[0]);body['reconcile']['balanced']=False;body['reconcile']['unbalanced_batches']=['B004']
    body['archive']['ready']=False;body['archive']['unbalanced_batches']=['B004']
    db.execute('INSERT INTO runs(id,body) VALUES(?,?)',('UNBAL-E2E',json.dumps(body,ensure_ascii=False)))
    db.execute("INSERT INTO meta(key,value) VALUES('latest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('UNBAL-E2E',))
    db.commit();db.close()
    r=client.post('/api/runs/UNBAL-E2E/seal');assert r.status_code==422 and r.get_json()['code']=='UNBALANCED' and 'B004' in r.get_json()['message']
    page=client.get('/m7_archive').data.decode()
    assert '封存证据（已拦截）' in page and 'B004' in page and '归档已拦截' in page
    assert client.get('/api/archive/UNBAL-E2E/export.csv').status_code==422

def test_tampered_resubmit_rejected(client):
    sid=client.post('/api/runs',json={'sample':'dirty.csv'}).get_json()['run_id']
    client.post('/api/runs/'+sid+'/seal')
    import sqlite3,json,os
    db=sqlite3.connect(os.environ['DB_PATH']);row=db.execute('SELECT body FROM runs WHERE id=?',(sid,)).fetchone()
    body=json.loads(row[0]);body['calculations'][0]['code']='PASS' if body['calculations'][0]['code']!='PASS' else 'FAIL'
    body['archive']['content_sha256']='0'*64
    db.execute('INSERT OR REPLACE INTO runs(id,body,sealed,content_sha256) VALUES(?,?,1,?)',(sid,json.dumps(body,ensure_ascii=False),'a'*64))
    db.commit();db.close()
    # 同源重跑产生正确校验值，与库中被改换的证据冲突时拒绝覆盖
    r=client.post('/api/runs',json={'sample':'dirty.csv'})
    assert r.status_code==409 and r.get_json()['code']=='EVIDENCE_CHANGED'
