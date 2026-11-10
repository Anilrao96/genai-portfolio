"""Check a recorded Clearflow Docker run through the existing Agent Eval Lab."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'projects/p09_docker_agent/eval_cases.jsonl'
sys.dont_write_bytecode = True


def outcomes(capture):
    repair = capture['repair']['result']
    repeat = capture['repeat']['result']
    volume = capture['audit_volume']
    first = capture['first_start']
    recreated = capture['recreated']
    missing = capture['missing_model_healthcheck']
    runtime = capture['runtime']
    return {
        'readiness': {'first_health': first['health'], 'recreated_health': recreated['health'],
                      'missing_model_exit': missing['exit'], 'missing_model_message': missing['output']},
        'repair': {'http_status': capture['repair']['http_status'], 'status': repair['status'],
                   'plan_origin': repair['plan_origin'], 'model_calls': repair['model_calls_this_request'],
                   'valid_before': repair['before']['valid_rows'], 'valid_after': repair['after']['valid_rows']},
        'duplicate': {'http_status': capture['repeat']['http_status'], 'status': repeat['status'],
                      'idempotent_replay': repeat['idempotent_replay'], 'model_calls': repeat['model_calls_this_request'],
                      'same_batch': repair['batch_id'] == repeat['batch_id'],
                      'same_revision': repair['committed_revision'] == repeat['current_active_revision']},
        'persistence': {'container_changed': first['container'] != recreated['container'],
                        'volume_retained': volume['retained_after_down'],
                        'snapshot_and_batch_unchanged': volume['snapshot_and_batch_unchanged'],
                        'browser_reopened_trace': capture['browser']['persisted_repair_trace_opened'],
                        **capture['snapshot']['totals']},
        'boundary': {key: runtime[key] for key in ('nonroot_uid_gid', 'root_read_only', 'capabilities_dropped',
                                                   'published_ports', 'windows_bind')},
    }


async def evaluate(args):
    lab = args.eval_lab_root.resolve()
    if not (lab / 'agent_eval/models.py').is_file():
        raise ValueError('Provide the existing Agent Eval Lab checkout.')
    if not args.out.resolve().is_relative_to(ROOT):
        raise ValueError('Keep the evaluation reports inside the portfolio workspace.')
    sys.path.insert(0, str(lab))
    from agent_eval.dataset import load_dataset
    from agent_eval.models import Prediction, ToolEvent
    from agent_eval.report import write_artifacts
    from agent_eval.runner import RunConfig, run_suite

    source = args.capture.read_bytes().replace(b'\r\n', b'\n')
    capture = json.loads(source)
    if capture.get('complete') is not True:
        raise ValueError('The capture must include a completed Docker probe.')
    answers = outcomes(capture)
    repair_trace = [ToolEvent(name=event['step'],
                             arguments={key: event[key] for key in ('attempt', 'rows', 'base_revision') if key in event})
                    for event in capture['repair']['result']['trace']]

    class RecordedDocker:
        name = 'recorded-docker-agent-replay-v1'

        async def predict(self, item):
            trace = repair_trace if item.prompt == 'repair' else []
            return Prediction(answer=json.dumps(answers[item.prompt]), trace=trace)

    cases, fingerprint = load_dataset(DATASET)
    run = await run_suite(cases, fingerprint, RecordedDocker(), RunConfig(concurrency=1, timeout_s=5),
                          provenance={'mode': 'recorded_docker_contract_replay',
                                      'capture_sha256': hashlib.sha256(source).hexdigest(),
                                      'capture_line_endings': 'lf',
                                      'model': capture['model'], 'docker': capture['docker'], 'compose': capture['compose'],
                                      'fresh_model_calls': False, 'fresh_container_execution': False,
                                      'trace_note': 'ToolEvent records the captured Clearflow repair stages.',
                                      'latency_note': 'Replay overhead. Actual startup and HTTP timings are in the capture.'})
    write_artifacts(run, args.out)
    report = args.out / 'report.html'
    html = report.read_text(encoding='utf-8')
    html = html.replace('LIVE ADAPTER — Scores apply to this curated dataset and configuration. Review failures and validate with representative held-out production data.',
                        'RECORDED DOCKER RUN — Checks use the saved run. No new model calls or containers.')
    html = html.replace('P95 LATENCY', 'P95 REPLAY OVERHEAD').replace('Wall time including retry backoff', 'Local replay duration')
    html = html.replace('TOOL TRACE', 'RECORDED STAGES')
    report.write_text(html, encoding='utf-8', newline='\n')
    summary = run['summary']
    print(json.dumps({key: summary[key] for key in ('passed', 'count', 'errors')}))
    return int(summary['passed'] != summary['count'] or summary['errors'] != 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval-lab-root', type=Path, default=ROOT.parent / 'agent-eval-lab')
    parser.add_argument('--capture', type=Path, default=ROOT / 'docs/docker-agent-live.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/docker-agent-eval')
    try:
        sys.exit(asyncio.run(evaluate(parser.parse_args())))
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f'Evaluation setup failed: {type(error).__name__}. Check the capture, dataset and output directory.')
