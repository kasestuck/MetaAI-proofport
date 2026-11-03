"""Standard-library entry point; backend execution dependencies load only on run."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=(
    '01_python_legacy_migration','02_python_math_edge_cases','03_python_compatibility',
    '04_python_sql_injection','05_python_unsafe_eval','06_python_secrets_crypto',
    '07_php_legacy_migration','08_php_xss','09_php_command_injection','10_php_security_regression',
)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Ten offline Proofport judge scenarios. No Meta calls, pulls or host project execution.')
    parser.add_argument('--scenario',help='One scenario number (01..10) or full ID; omit for all ten')
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--verify-summary',type=Path,help='Recheck a saved summary/receipts; execute no project')
    args=parser.parse_args(argv)
    if args.verify_summary and (args.scenario or args.list): parser.error('Use --verify-summary alone')
    selected=SCENARIOS
    if args.scenario:
        selected=tuple(s for s in SCENARIOS if s==args.scenario or s[:2]==args.scenario.zfill(2))
        if len(selected)!=1: parser.error('Select 01..10 or one listed full scenario ID')
    if args.list:
        for name in selected:
            data=json.loads((ROOT/'judge_tests'/name/'scenario.json').read_text(encoding='utf-8'))
            print(name+' | '+data['language']+' | '+data['operation'])
        return 0
    if sys.version_info[:2]!=(3,12): parser.error('Use Python 3.12 and the pinned backend requirements')
    sys.path.insert(0,str(ROOT))
    try:
        from backend.judge_suite import run_suite,verify_summary
        if args.verify_summary:
            if args.scenario or args.list: parser.error('Use --verify-summary alone')
            summary=verify_summary(args.verify_summary);path=args.verify_summary
        else: summary,path=run_suite(selected)
    except ImportError:
        print('Install backend/requirements.txt in .venv, then retry. No project code or model was run.');return 2
    except (OSError,ValueError,KeyError,TypeError,RuntimeError):
        print('Judge setup or saved integrity check failed. No fallback; inspect local files.');return 2
    for result in summary['scenarios']:
        print(result['status']+' '+result['name']+' - '+result['reason'])
    print('JSON summary: '+str(path))
    print('New Meta API calls: 0. NEEDS_REVIEW is not an accepted fix.')
    return 0 if summary['mandatory_checks_passed'] else 1


if __name__=='__main__': raise SystemExit(main())
