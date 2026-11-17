def execute(state):
    reconcile=state.get('reconcile',{})
    state['archive']={
        'evidence_count':len(state.get('calculations',[]))+len(state['quarantine']),
        'ready':bool(reconcile.get('balanced',False)),
        'unbalanced_batches':reconcile.get('unbalanced_batches',[])}
    return state
