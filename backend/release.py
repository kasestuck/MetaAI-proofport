"""Local release audit and saved-real-run exports. Never constructs an LLM client.

Generated packs remain ignored. This tool cannot publish, grant paid permission,
run project code or certify submission readiness.
"""
import argparse
import base64
from hashlib import sha256
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from uuid import uuid4

from dotenv import dotenv_values

from backend.ai import artifacts, first_live, first_php_live, first_security_live
from backend.core.models import RunState
from backend.core.projects import copy_project, linked
from backend.languages.base import inventory, hashes

ROOT=Path(__file__).resolve().parents[1]
SAVED={
    'python':('p8-mathutils-bec88702e50948428fe35e2fa029af3e','samples/legacy_shop','28b81b24a608e38112841788095f3ddd3835f4a493937b2851d52f27e930e123'),
    'php':('p83-php-39cfcb6a2adf49a99b9948db31e01870','tests/fixtures/php_shop','8ff0aac59cb4f6e29963e3f080c9718700b02658a455918e20d107b17184accc'),
    'security':('p84-security-afc0c284439542fa999c2d5a8b58999d','samples/legacy_shop','f7670a32d20506c452e0de09ac2ec8bc2d36e037a701cd3d65b3382ead3bb612'),
}
FORMAT='proofport_saved_live_projection_v1'
TOKEN_PATTERN=re.compile(rb'(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})')


def digest(path): return sha256(path.read_bytes()).hexdigest()


def credential_forms(root):
    values=[dotenv_values(root/p).get('MODEL_API_KEY') for p in ('.env','backend/.tmp/meta-smoke.env')]
    return {form for value in values if value for form in (value.encode(),base64.b64encode(value.encode()),json.dumps(value)[1:-1].encode())}


def secret_free(data,forms):
    return not TOKEN_PATTERN.search(data) and not any(value in data for value in forms)


def project_check(source,expected):
    base,files=inventory(source)
    if hashes(base,files)!=expected: raise ValueError('Original project byte hashes differ')


def checked_path(root,name):
    p=PurePosixPath(name)
    if not isinstance(name,str) or p.is_absolute() or '\\' in name or ':' in name or any(x in {'','.','..'} for x in name.split('/')):
        raise ValueError('Unsafe release artifact path')
    path=root.joinpath(*p.parts)
    if any(linked(part) for part in (path,*path.parents)) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Linked/escaped release artifact')
    return path


def verify_recording(kind,folder,source):
    if digest(folder/'report.json')!=SAVED[kind][2]: raise ValueError('Historical report differs from documented proof')
    check=lambda expected:project_check(source,expected)
    if kind=='python': first_live.verify_export(folder,original_check=check)
    else: artifacts.verify(folder,check)
    return json.loads((folder/'report.json').read_text(encoding='utf-8'))


def projection(kind,raw):
    """Display projection only. Preserve raw evidence; never synthesize events."""
    if raw.get('mode')!='live' or raw.get('model_calls')!=1 or not raw.get('chain_intact') or not raw.get('originals_unchanged'):
        raise ValueError('Expected intact one-call historical live record')
    isolation=raw.get('isolation','')
    if not isinstance(isolation,str) or not (isolation=='docker' or isolation.startswith('docker: ')):
        raise ValueError('Expected recorded Docker isolation')
    security=kind=='security';language='php' if kind=='php' else 'python'
    if security:
        if raw.get('finding_status')!='needs_review' or raw.get('ai_security_fix') is not False or any(a['applied'] for a in raw['attempts']):
            raise ValueError('Expected rejected protected eval proposal')
        last=raw['attempts'][-1];checks=last['checks'];comparisons=checks['golden']['comparisons'];target=checks['existing_tests']
        syntax=checks['syntax']['passed'];tests=target['passed'] if 'passed' in target else all(o['status']=='passed' for o in target['outcomes'])
        behavior=checks['golden']['passed'];module=raw['finding']['file']
        details=[{**raw['finding'],'status':'needs_review'},*last['rescan']['findings']]
        findings={f['id']:f for f in details}
        fix={'mode':'live','ai_generated':True,'status':'needs_review','attempts':raw['attempts'],
             'findings_before':[raw['finding']],'findings_after':last['rescan']['findings'],'decisions':list(findings.values()),
             'fixed':[],'needs_review':[raw['finding']['id']],'rejected':[a['id'] for a in raw['attempts']],
             'original_unchanged':raw['originals_unchanged'],'evidence_chain_intact':raw['chain_intact']}
    else:
        if raw.get('status')!='done' or raw.get('ai_migration') is not True: raise ValueError('No verified historical migration')
        it=raw['iterations'][-1];checks=it.get('checks',{})
        comparisons=checks['golden']['comparisons'] if kind=='php' else it['comparisons']
        target=checks['existing_tests'] if kind=='php' else it['target_tests']
        syntax=raw.get('syntax_passed',it.get('syntax_passed'));tests=raw.get('tests_passed',it.get('tests_passed'))
        behavior=raw.get('behavior_verified',it.get('behavior_verified'));module=raw.get('file') or raw['target_file']
        if not all(value is True for value in (syntax,tests,behavior)) or not target['outcomes'] or any(o['status']!='passed' for o in target['outcomes']):
            raise ValueError('Historical checks do not establish an accepted migration')
        findings={};fix=None
    passed=sum(c['matches'] for c in comparisons);total=len(comparisons)
    if (total,passed,target['tests_run'])!=((9,5,1) if security else (22,22,9) if kind=='php' else (31,31,3)):
        raise ValueError('Historical scope/result changed; no demo substitution')
    v={'language':language,'mode':'security_fix' if security else 'migration','model':raw['model'],'model_calls':raw['model_calls'],'isolation_description':isolation,
       'ai_migration':not security,'comparisons':comparisons,'legacy_tests':raw['source_tests'],'source_tests':raw['source_tests'],
       'target_tests':target,'target_compiles':syntax,'source_python':raw.get('source_python'),
       'source_version':'7.4' if kind=='php' else '2.7','target_version':'8.3' if kind=='php' else '2.7' if security else '3.12',
       'historical':{'format':FORMAT,'kind':kind,'source_report_sha256':SAVED[kind][2],
           'new_api_calls':0,'security_scanned':security,'notice':'Saved real Meta run. Display projection, not a new execution or external attestation.'},
       'compatibility':{'level':'not_verified' if security else 'behavior_verified','syntax_compatible':syntax,'syntax_passed':syntax,
           'tests_passed':tests,'recorded_cases_match':behavior,'behavior_verified':behavior,'comparisons':comparisons,'existing_tests':target},
       'limitations':raw.get('limitations',[])+['Historical finite-scope results; replay makes no new API call or compatibility claim for different inputs.']}
    if fix: v.update(security_fix=fix,security_details=list(findings.values()))
    state={'status':'failed' if security else 'done','phase':'security' if security else 'reporting','isolation':'docker',
       'modules':[{'name':module,'status':'failed' if security else 'green','iterations':len(raw['attempts'] if security else raw['iterations']),
                   'tests_passed':passed,'tests_total':total}],
       'security':{'before':1 if security else 0,'after':len(raw['attempts'][-1]['rescan']['findings']) if security else 0,
          'findings':[{k:f[k] for k in ('id','file','line','severity','status','note')} for f in findings.values()]},
       'hashes':{**raw['original_hashes'],'unchanged':raw['originals_unchanged']},'chain_intact':raw['chain_intact'],
       'metrics':{'tests_passed':passed,'tests_total':total,'tokens_in':sum(x['tokens_in'] for x in raw['usage']),
                  'tokens_out':sum(x['tokens_out'] for x in raw['usage']),'cost_usd':sum(x['cost_usd'] for x in raw['usage'])}}
    if security: state['error']={'code':raw['error']['code'],'message':'Recorded proposal rejected: 5/9 cases, 0/1 tests; next request blocked locally. Manual review required.'}
    RunState.model_validate(state)
    return {'state':state,'simulation':False,'settings':{'pipeline':'live','model':raw['model'],'max_iterations':raw['limits']['max_calls']},
            'verification':v,'events':raw['events'],'notice':v['historical']['notice']}


def prepare_demo(root=ROOT):
    forms=credential_forms(root)
    records={kind:verify_recording(kind,root/'backend/.work'/entry[0],root/entry[1]) for kind,entry in SAVED.items()}
    # All old seals/sources are checked before creating a new export directory.
    output=root/'backend/.work'/('p10-demo-'+uuid4().hex);output.mkdir()
    source_root=output/'sources';source_root.mkdir()
    for source in {'samples/legacy_shop','tests/fixtures/php_shop'}: copy_project(root/source,source_root/Path(source).name)
    for kind,raw in records.items():
        original=root/'backend/.work'/SAVED[kind][0];target=output/kind;target.mkdir()
        names=set(raw['artifact_hashes'])|{'report.json','report.html','report_receipt.json' if kind=='python' else 'report-receipt.json'}
        for name in names:
            src=checked_path(original,name);dst=checked_path(target,name);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        shown=projection(kind,raw)
        (output/('proofport-'+kind+'.json')).write_text(json.dumps(shown,indent=2,ensure_ascii=False),encoding='utf-8')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Proofport saved real evidence</title>'
        '<h1>Saved genuine Meta runs - no new API calls</h1><p>Import proofport-*.json into the dashboard. Raw original reports remain unchanged.</p>'
        +''.join('<p><a href="'+k+'/report.html">'+escape(k)+' original report</a></p>' for k in records),encoding='utf-8')
    files={p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file()}
    if any(not secret_free((output/name).read_bytes(),forms) for name in files): raise ValueError('Export withheld: possible credential; private inspection required')
    (output/'manifest.json').write_text(json.dumps({'format':FORMAT,'new_api_calls':0,'files':files},indent=2),encoding='utf-8')
    verify_demo(output)
    shutil.make_archive(str(output),'zip',output)
    return output


def verify_demo(folder):
    folder=Path(folder).absolute();manifest=checked_path(folder,'manifest.json')
    if manifest.stat().st_size>2_000_000: raise ValueError('Pack manifest exceeds size bound')
    paths=list(folder.rglob('*'))
    if len(paths)>6000 or any(linked(p) for p in paths): raise ValueError('Linked/oversized pack inventory')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('format')!=FORMAT or data.get('new_api_calls')!=0 or not 1<=len(data['files'])<=5000: raise ValueError('Invalid pack manifest')
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual!=set(data['files'])|{'manifest.json'}: raise ValueError('Pack file inventory changed')
    for name,value in data['files'].items():
        path=checked_path(folder,name)
        if path.stat().st_size>8_000_000 or digest(path)!=value: raise ValueError('Pack bytes differ or exceed size bound')
    for kind,entry in SAVED.items():
        raw=verify_recording(kind,folder/kind,folder/'sources'/Path(entry[1]).name)
        shown=json.loads((folder/('proofport-'+kind+'.json')).read_text(encoding='utf-8'))
        if shown!=projection(kind,raw): raise ValueError('Display projection differs from raw proof')
    return True


def git(root,*args,input=None):
    return subprocess.run(['git','-C',str(root),*args],input=input,capture_output=True,check=True).stdout


def audit(root=ROOT):
    tracked=[p for p in git(root,'ls-files','-z').decode().split('\0') if p]
    generated=[p for p in tracked if set(Path(p).parts)&{'.work','.tmp','.venv','venv','__pycache__','.pytest_cache','node_modules','work'} or p.endswith(('.pyc','.pyo'))]
    envs=[p for p in tracked if Path(p).name=='.env' or Path(p).name.endswith('.env') or Path(p).name.startswith('.env.') and Path(p).name!='.env.example']
    forms=credential_forms(root)
    ids=[line.split(b' ')[0] for line in git(root,'rev-list','--objects','--all').splitlines()]
    metadata=git(root,'cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)',input=b'\n'.join(ids)+b'\n')
    blobs=[row.split()[0] for row in metadata.splitlines() if row.split()[1]==b'blob']
    sizes=[int(row.split()[2]) for row in metadata.splitlines() if row.split()[1]==b'blob']
    if sum(sizes)>100_000_000: raise ValueError('History scan exceeds bounded audit size; manual review required')
    stream=git(root,'cat-file','--batch',input=b'\n'.join(blobs)+b'\n');cursor=0;hits=0
    for _ in blobs:
        end=stream.index(b'\n',cursor);size=int(stream[cursor:end].split()[2]);start=end+1
        hits+=not secret_free(stream[start:start+size],forms);cursor=start+size+1
    current_hits=sum(not secret_free((root/p).read_bytes(),forms) for p in tracked if (root/p).is_file())
    required=['README.md','AGENTS.md','LICENSE','SECURITY.md','THIRD_PARTY_NOTICES.md','.gitignore','pytest.ini','.env.example']
    missing=[p for p in required if not (root/p).is_file()]
    return {'branch':git(root,'branch','--show-current').decode().strip(),'working_tree_clean':not git(root,'status','--porcelain').strip(),'tracked_files':len(tracked),
        'history_blobs_checked':len(blobs),'known_credential_checked':bool(forms),'credential_scope':'Known local key/JSON/base64 and common token prefixes; not exhaustive secret discovery.',
        'historical_credential_hits':hits,'current_credential_hits':current_hits,'tracked_generated_files':generated,
        'tracked_private_env_files':envs,'missing_release_files':missing,
        'technical_checks_passed':not any((hits,current_hits,generated,envs,missing)),
        'scope':'Local Git/file checks only; public access, video, team, organizer rules and submission are separate manual gates.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('audit','prepare-demo','verify-demo'));parser.add_argument('--pack',type=Path)
    args=parser.parse_args()
    try:
        if args.operation=='audit':
            result=audit();print(json.dumps(result,indent=2));return int(not result['technical_checks_passed'])
        if args.operation=='prepare-demo':
            if args.pack: raise ValueError('Prepare always creates a new ignored workspace')
            output=prepare_demo();print(json.dumps({'pack':str(output),'zip':str(output)+'.zip','new_api_calls':0}));return 0
        if not args.pack: raise ValueError('Select an explicit saved pack')
        verify_demo(args.pack);print('Saved real-run pack verified; no new execution or API call.');return 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError,subprocess.SubprocessError):
        print('Release check blocked. No fallback or model call; inspect local prerequisites privately.');return 2


if __name__=='__main__': raise SystemExit(main())
