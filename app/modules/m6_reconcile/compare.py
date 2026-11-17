from collections import defaultdict
RANK={'PASS':0,'UNCERTAIN':1,'FAIL':2}

def balance(state):
    accepted=len(state['rows']);isolated=len(state['quarantine'])
    accounted=accepted+isolated+state['blank_count']+state['header_count']+state['duplicate_count']
    batches=defaultdict(list)
    for r in state['calculations']:batches[r['batch']].append(r)
    # 按批次独立记账：每批纳入裁决的项目数与样本数必须和该批账页相符。
    accounts={b:{'projects':len(rows),'samples':len({r['sample_id'] for r in rows})}
              for b,rows in batches.items()}
    grades=[]
    unbalanced_batches=[]
    for b,rows in sorted(batches.items()):
        account=accounts[b]
        grade={'batch':b,
               'code':max((r['code'] for r in rows),key=lambda c:RANK[c]),
               'projects':len(rows),'samples':len({r['sample_id'] for r in rows}),
               'account_projects':account['projects'],'account_samples':account['samples']}
        grade['batch_balanced']=(grade['account_projects']==grade['projects']
                                 and grade['account_samples']==grade['samples'])
        if not grade['batch_balanced']:unbalanced_batches.append(b)
        grades.append(grade)
    total_balanced=accounted==state['input_count']
    return {'input':state['input_count'],'accepted':accepted,'isolated':isolated,
            'blank':state['blank_count'],'headers':state['header_count'],
            'duplicates':state['duplicate_count'],'accounted':accounted,
            'balanced':total_balanced and not unbalanced_batches,
            'business':state['business'],'grades':grades,
            'unbalanced_batches':sorted(set(unbalanced_batches) | ({'*总账*'} if not total_balanced else set()))}
