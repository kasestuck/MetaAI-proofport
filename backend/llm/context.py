"""Local request size accounting. No provider tokenizer or network is implied."""

import json


def measure(system, user, allowance):
    size = len(json.dumps([{"role":"system","content":system}, {"role":"user","content":user}],
                          ensure_ascii=False).encode('utf-8'))
    return {'utf8_bytes':size, 'framing_allowance':256, 'conservative_input_units':size+256,
            'input_allowance':allowance, 'within_allowance':size+256 <= allowance,
            'method':'utf8_bytes_plus_framing_not_provider_tokenizer'}


def schema_without_titles(value):
    if isinstance(value,dict): return {k:schema_without_titles(v) for k,v in value.items() if k not in {'title','description'}}
    if isinstance(value,list): return [schema_without_titles(v) for v in value]
    return value


def deltas(expected, actual, path='$', limit=8):
    """Minimal differing observations, never remove the full local recordings."""
    result=[]
    def visit(old,new,location):
        if len(result)>=limit or old==new: return
        if isinstance(old,dict) and isinstance(new,dict) and old.get('t')==new.get('t') and set(old)==set(new):
            for key in sorted(old): visit(old[key],new[key],location+'.'+key)
        elif isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
            for i,(a,b) in enumerate(zip(old,new)): visit(a,b,location+'[%d]'%i)
        else: result.append({'path':location,'expected':old,'actual':new})
    visit(expected,actual,path)
    return result


def compact_failures(failures):
    if not isinstance(failures,dict): return failures
    result={k:v for k,v in failures.items() if k in {'repair_requested','manual_review_required','requirements'}}
    for stage in ('syntax','runtime_api','golden','existing_tests'):
        data=failures.get(stage) or {}
        result[stage]={k:data[k] for k in ('passed','errors') if k in data}
    result['failing_cases']=[{'input':case['input'], 'differences':deltas(case.get('expected'),case.get('actual'))}
                             for case in failures.get('failing_cases',[])[:8]]
    return result


def previous_excerpt(previous, finding):
    """Explicitly labelled diagnostic excerpts; never pretend this is full code."""
    from hashlib import sha256
    lines=previous.splitlines()
    selected=set()
    # P8.4's confirmed incompatible API references, plus the bound function.
    for index,line in enumerate(lines):
        if any(s in line for s in ('ast.Bytes','ast.Constant','ast.NameConstant','def '+finding.get('scope','parse_value')+'(')):
            selected.update(range(max(0,index-2),min(len(lines),index+5)))
    if not selected: selected.update(range(min(len(lines),20)))
    selected=sorted(selected)[:60]
    return {'mode':'diagnostic_excerpts_not_complete_candidate','sha256':sha256(previous.encode()).hexdigest(),
            'total_lines':len(lines),'omitted_lines':len(lines)-len(selected),
            'lines':[{'line':i+1,'text':lines[i]} for i in selected]}
