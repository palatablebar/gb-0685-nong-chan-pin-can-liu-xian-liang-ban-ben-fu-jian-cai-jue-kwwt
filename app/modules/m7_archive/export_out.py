import io,csv,json,hashlib

def signed_payload(state):
    """参与校验值的稳定证据：运行清单稳定区、对账、计算证据与隔离原因。
    处理耗时、生成时刻等运行信息不进入校验值，同源重新核验结果一致。"""
    return {'manifest':state.get('manifest',{}).get('signed',{}),
        'run_id':state.get('run_id','preview'),
        'reconcile':state.get('reconcile',{}),
        'calculations':state.get('calculations',[]),
        'quarantine':state.get('quarantine',[])}

def canonical(state):
    return json.dumps(signed_payload(state),sort_keys=True,ensure_ascii=False,
        separators=(',',':')).encode('utf-8')

def bundle(state):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['记录类型','批次','来源行','业务ID','原因码','内容'])
    rid=state.get('run_id','preview')
    writer.writerow(['运行清单',rid,'','','',json.dumps(state.get('manifest',{}),ensure_ascii=False,sort_keys=True)])
    writer.writerow(['对账',rid,'','','',json.dumps(state.get('reconcile',{}),ensure_ascii=False,sort_keys=True)])
    for row in state.get('calculations',[]):writer.writerow(['计算',rid,row.get('line',''),row.get('id',''),row.get('code',''),json.dumps(row,ensure_ascii=False,sort_keys=True)])
    for row in state['quarantine']:writer.writerow(['隔离',rid,row['line'],row.get('id',''),row['code'],json.dumps(row.get('raw',{}),ensure_ascii=False,sort_keys=True)])
    return '﻿'+out.getvalue()

def checksum(state):
    """证据内容校验值：只对稳定业务证据取摘要，与耗时、生成时刻无关。"""
    return hashlib.sha256(canonical(state)).hexdigest()
