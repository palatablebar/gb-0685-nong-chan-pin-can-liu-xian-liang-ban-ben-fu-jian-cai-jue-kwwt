import hashlib,json
from datetime import datetime,timezone
from app.config import RULE_VERSION

def identity(content, parameters):
    raw = content + json.dumps(parameters,sort_keys=True,ensure_ascii=False).encode() + RULE_VERSION.encode()
    return hashlib.sha256(raw).hexdigest()[:20]

def sealed_manifest(content, parameters):
    """进入证据校验值的稳定部分：同源重跑保持不变，不含耗时与生成时刻。"""
    return {'source_sha256':hashlib.sha256(content).hexdigest(),'rule_version':RULE_VERSION,
        'parameters':parameters or {},'timezone':'Asia/Shanghai'}

def manifest(content, parameters, elapsed):
    """完整运行清单：稳定区(signed)可复核业务内容，运行区(runtime)只记录本次处理何时发生。"""
    return {'signed':sealed_manifest(content,parameters),
        'runtime':{'elapsed_ms':round(elapsed*1000),
                   'generated_at':datetime.now(timezone.utc).isoformat()}}
