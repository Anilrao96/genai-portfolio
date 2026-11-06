"""Reuse Agent Eval Lab to check recorded pipeline outcomes and workflow stages, with no inference."""
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

    class RecordedPipeline:
        name='recorded-pipeline-live-stage-replay-v1'
        async def predict(self,item):
            response=records[item.prompt]
            answer=json.dumps({'status':response['status'],'plan_origin':response['plan_origin'],
                'valid_rows':response['after']['valid_rows'] if response['after'] else None,
                'model_calls_this_request':response['model_calls_this_request']})
            events=[ToolEvent(name=e['step'],arguments={k:v for k,v in e.items() if k!='step'},output=e.get('report')) for e in response['trace']]
            usage=[e['usage'] for e in response['trace'] if e['step']=='propose']
            return Prediction(answer=answer,trace=events,input_tokens=sum(u.get('input_tokens') or 0 for u in usage),
                output_tokens=sum(u.get('output_tokens') or 0 for u in usage),cost_usd=None)

    cases,fingerprint=load_dataset(ROOT/'projects/p05_self_healing_pipeline/eval_cases.jsonl')
    run=await run_suite(cases,fingerprint,RecordedPipeline(),RunConfig(concurrency=1,timeout_s=5),
        provenance={'mode':'recorded_live_stage_replay','model':evidence['model'],'capture_sha256':hashlib.sha256(source).hexdigest(),
            'fresh_model_calls':False,'trace_note':'ToolEvent entries represent recorded pipeline stages, not MCP or remote tools.',
            'latency_note':'Replay overhead only; real HTTP/model timings are in the source capture.',
            'evaluates':'Authored outcome and stage-path contracts, not arbitrary repair semantics or production data quality.'})
    write_artifacts(run,args.out)
    report=args.out/'report.html'
    text=report.read_text(encoding='utf8').replace('LIVE ADAPTER —','RECORDED PIPELINE STAGE REPLAY — No new model calls; timing below is replay overhead.')
    text=text.replace('P95 LATENCY','P95 REPLAY OVERHEAD').replace('Wall time including retry backoff','Not an inference performance measurement')
    report.write_text(text,encoding='utf8',newline='\n')
    summary=run['summary'];print(json.dumps({'mode':'recorded_live_stage_replay','passed':summary['passed'],'count':summary['count'],'errors':summary['errors']}))
    return 0 if summary['passed']==summary['count'] and not summary['errors'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval-lab-root',type=Path,default=ROOT.parent/'agent-eval-lab')
    parser.add_argument('--capture',type=Path,default=ROOT/'docs/pipeline-live.json')
    parser.add_argument('--out',type=Path,default=ROOT/'docs/pipeline-eval')
    args=parser.parse_args()
    try:sys.exit(asyncio.run(main(args)))
    except (ValueError,KeyError,OSError) as error:
        print(f'Evaluation setup failed: {type(error).__name__}',file=sys.stderr);sys.exit(2)
