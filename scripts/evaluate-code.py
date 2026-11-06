"""Existing Agent Eval Lab replay of captured code outcomes, without new model calls or execution."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True


async def main(args):
    lab=args.eval_lab_root.resolve()
    if not (lab/'agent_eval/models.py').is_file():raise ValueError('Provide the existing Agent Eval Lab checkout.')
    sys.path.insert(0,str(lab))
    from agent_eval.dataset import load_dataset
    from agent_eval.models import Prediction,ToolEvent
    from agent_eval.report import write_artifacts
    from agent_eval.runner import RunConfig,run_suite
    source=args.capture.read_bytes();evidence=json.loads(source)
    if not evidence.get('complete') or not evidence.get('passed'):raise ValueError('Complete passing live capture required.')
    records={case['id']:case['response'] for case in evidence['cases']}
    if len(records)!=len(evidence['cases']):raise ValueError('Duplicate captured case IDs.')

    class RecordedCode:
        name='recorded-code-native-isolation-replay-v1'
        async def predict(self,item):
            response=records[item.prompt]
            executions=[a['execution'] for a in response['attempts'] if a['execution']]
            native=bool(executions) and all(e['engine_policy']['network']=='none' and not e['engine_policy']['host_mounts']
                and e['kernel_policy']['uid']==65534 and e['kernel_policy']['no_new_privileges'] for e in executions)
            answer=json.dumps({'status':response['status'],'executions':response['executions'],'model_calls':response['model_calls'],
                'tests_passed':response['attempts'][-1].get('tests_passed'),'native_isolation':native})
            events=[ToolEvent(name=e['stage'],arguments={k:v for k,v in e.items() if k not in ('stage','code')},output=e.get('feedback')) for e in response['trace']]
            usage=[e['usage'] for e in response['trace'] if 'usage' in e]
            return Prediction(answer=answer,trace=events,input_tokens=sum(u.get('input_tokens') or 0 for u in usage),
                output_tokens=sum(u.get('output_tokens') or 0 for u in usage),cost_usd=None)

    cases,fingerprint=load_dataset(ROOT/'projects/p06_code_assistant/eval_cases.jsonl')
    run=await run_suite(cases,fingerprint,RecordedCode(),RunConfig(concurrency=1,timeout_s=5),provenance={
        'mode':'recorded_live_stage_replay','model':evidence['model'],'capture_sha256':hashlib.sha256(source).hexdigest(),
        'fresh_model_calls':False,'fresh_candidate_execution':False,
        'trace_note':'ToolEvents represent recorded LangGraph stages; policy fields are captured observations.',
        'latency_note':'Replay overhead only; actual timings are in the source capture.',
        'evaluates':'Small authored outcome and stage contracts; does not rerun isolation controls or establish general program correctness.'})
    write_artifacts(run,args.out)
    report=args.out/'report.html'
    text=report.read_text(encoding='utf8').replace('LIVE ADAPTER —','RECORDED CODE STAGE REPLAY — No inference or candidate execution; timing below is replay overhead.')
    text=text.replace('P95 LATENCY','P95 REPLAY OVERHEAD').replace('Wall time including retry backoff','Not an inference performance measurement')
    report.write_text(text,encoding='utf8',newline='\n')
    summary=run['summary'];print(json.dumps({'mode':'recorded_live_stage_replay','passed':summary['passed'],'count':summary['count'],'errors':summary['errors']}))
    return 0 if summary['passed']==summary['count'] and not summary['errors'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval-lab-root',type=Path,default=ROOT.parent/'agent-eval-lab')
    parser.add_argument('--capture',type=Path,default=ROOT/'docs/code-assistant-live.json')
    parser.add_argument('--out',type=Path,default=ROOT/'docs/code-eval')
    args=parser.parse_args()
    try:sys.exit(asyncio.run(main(args)))
    except (ValueError,KeyError,OSError) as error:
        print(f'Evaluation setup failed: {type(error).__name__}',file=sys.stderr);sys.exit(2)
