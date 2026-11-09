import asyncio
import base64
from datetime import datetime,timezone
import hashlib
import time
import uuid

from projects.p06_code_assistant.assistant import equal
from portfolio_core.ollama import ModelServiceError
from .contracts import Source
from .qa import CORE,QAReport,extra_cases
from . import runtime


def compare(responses,cases):
    if not isinstance(responses,list) or len(responses)!=len(cases):return [{'passed':False,'error':'The API did not return one response per request.'}]
    return [{'request':request,'expected':expected,'actual':actual,
             'passed':isinstance(actual,dict) and all(key in actual and equal(actual[key],value) for key,value in expected.items())}
            for actual,(request,expected) in zip(responses,cases)]


class AppBuilder:
    def __init__(self,backend,frontend,qa,store,executor=None,guard=None):
        self.backend,self.frontend,self.qa,self.store=backend,frontend,qa,store
        self.execute=executor or runtime.execute;self.guard=guard or runtime.ready

    async def run(self,spec,model):
        await asyncio.to_thread(self.guard)
        run={'id':uuid.uuid4().hex,'spec':spec.model_dump(),'model':model,'created_at':datetime.now(timezone.utc).isoformat(),
            'status':'running','model_calls':0,'build_attempts':0,'trace':[],'error':None,'limits':{'model_calls':6,'build_attempts':2,'workflow_seconds':540}}
        workspace=self.store.workspace(run['id']);files={};started=time.perf_counter()
        self.store.save(run)
        async def propose(role,name,feedback=None):
            if run['model_calls']>=6:raise ValueError('Six model-call budget exhausted.')
            run['model_calls']+=1;t=time.perf_counter()
            output,usage=await role.generate(spec,files.get(name,''),feedback)
            output=Source.model_validate(output);files[name]=output.code
            digest=workspace.write(name,output.code)
            run['trace'].append({'stage':'backend' if name=='backend.py' else 'frontend','source':output.code,'note':output.note,
                'source_sha256':digest,'usage':usage,'duration_ms':round((time.perf_counter()-t)*1000),'repair':feedback is not None})
            self.store.save(run)
        try:
            async with asyncio.timeout(540):
                await propose(self.backend,'backend.py');await propose(self.frontend,'App.jsx')
                for attempt in range(2):
                    run['build_attempts']+=1
                    execution=await asyncio.to_thread(self.execute,{'op':'validate','files':files,'requests':[c[0] for c in CORE]})
                    result=execution.get('result') or {};bundle=result.pop('bundle_base64',None)
                    tests=compare(result.get('responses',[]),CORE) if result.get('build_passed') else []
                    run['trace'].append({'stage':'build_and_core_qa','execution':execution,'tests':tests})
                    self.store.save(run)
                    if execution.get('termination_reason') or execution.get('exit_code') in (137,152):
                        run.update(status='limited',error='The isolated build exceeded an execution limit.');break
                    good=result.get('build_passed') and tests and all(test['passed'] for test in tests)
                    if not good:
                        if attempt==1:run.update(status='failed',error='Two isolated build attempts did not satisfy the contract.');break
                        name='App.jsx' if result.get('stage')=='frontend_build' else 'backend.py'
                        feedback={'runtime_error':execution.get('stderr','')[-2000:],'build_error':result.get('error'),
                                  'failed_tests':[test for test in tests if not test['passed']][:2]}
                        await propose(self.frontend if name=='App.jsx' else self.backend,name,feedback);continue
                    run['model_calls']+=1;t=time.perf_counter()
                    review,usage=await self.qa.review(spec,files,tests);review=QAReport.model_validate(review)
                    run['trace'].append({'stage':'qa_review','review':review.model_dump(),'usage':usage,'duration_ms':round((time.perf_counter()-t)*1000)})
                    if not review.approved:run.update(status='needs_review',error='The QA role withheld approval.');break
                    cases=CORE+extra_cases(review.scenarios)
                    checked=await asyncio.to_thread(self.execute,{'op':'backend_request','files':files,'requests':[case[0] for case in cases]})
                    extra_result=checked.get('result') or {}
                    verified=compare(extra_result.get('responses',[]),cases)
                    run['trace'].append({'stage':'qa_scenarios','execution':checked,'tests':verified})
                    if checked.get('termination_reason') or checked.get('exit_code') in (137,152):
                        run.update(status='limited',error='The isolated QA execution exceeded a limit.');break
                    if checked['exit_code'] or not all(test['passed'] for test in verified):
                        if attempt==1:run.update(status='failed',error='QA edge cases failed after the repair budget.');break
                        await propose(self.backend,'backend.py',{'actual_qa_failures':[v for v in verified if not v['passed']][:2],
                            'runtime_error':checked.get('stderr','')[-2000:]});continue
                    if not isinstance(bundle,str):raise ValueError('The isolated builder did not return a bundle.')
                    artifact=base64.b64decode(bundle,validate=True)
                    if len(artifact)>512000:raise ValueError('Built artifact exceeds limit.')
                    (workspace.path/'app.js').write_bytes(artifact)
                    run.update(status='passed',manifest=workspace.manifest(spec),bundle_sha256=hashlib.sha256(artifact).hexdigest(),
                        tests_passed=sum(test['passed'] for test in verified),tests_total=len(verified),qa=review.model_dump())
                    break
        except TimeoutError:run.update(status='timeout',error='App generation exceeded its 540-second budget.')
        except (runtime.IsolationError,ModelServiceError,ValueError) as exc:run.update(status='blocked' if isinstance(exc,runtime.IsolationError) else 'failed',error=str(exc)[:600])
        run['duration_ms']=round((time.perf_counter()-started)*1000);self.store.save(run);return run
