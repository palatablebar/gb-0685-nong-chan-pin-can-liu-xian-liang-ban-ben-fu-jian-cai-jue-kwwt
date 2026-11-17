import base64
from flask import request,render_template,jsonify
from app.errors import DomainError
from app.config import TITLE,MODULES,SHORT
from app.workflow import run,load
from app import store

def payload():
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):raise DomainError('PAYLOAD','请求必须是对象')
    if 'csv' in data and not isinstance(data['csv'],str):raise DomainError('CSV','CSV内容必须是文本')
    sample=data.get('sample',request.args.get('sample','dirty.csv'))
    content=data.get('csv')
    return (content.encode() if isinstance(content,str) else load(sample)),data.get('parameters',{})

def api(stage):
    content,parameters=payload();return jsonify(run(content,parameters,stage))

def page(stage,template):
    latest=store.history();state=store.get(latest[0]['id']) if latest else run(load('dirty.csv'),{})
    source=load(request.args['sample']) if 'sample' in request.args else base64.b64decode(state['source_b64']) if state.get('source_b64') else load('dirty.csv')
    data=run(source,state.get('manifest',{}).get('signed',{}).get('parameters',{}),stage)
    if stage==7 and latest:
        # 归档页以已存储批次的对账结论、封存状态与稳定校验值为准，
        # 重算只用于展示明细；同源重跑不会改换已确认证据。
        stored=store.get(latest[0]['id'])
        data['reconcile']=stored.get('reconcile',data.get('reconcile',{}))
        data['archive']=stored.get('archive',data.get('archive',{}))
        data['run_id']=stored['run_id']
    return render_template(template,title=TITLE,short=SHORT,modules=MODULES,current=stage,data=data,run=state,history=latest)
