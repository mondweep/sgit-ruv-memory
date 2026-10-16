"""Opt-in Ruflo CLI recovery acceptance run; no cloud credentials needed.
Run from project root: python scripts/validate_ruflo_recall.py --runtime /tmp/ruflo-recall-runtime
"""
import argparse,contextlib,hashlib,json,os,re,shutil,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sgit_ruv_memory.core import Adapter
from sgit_ruv_memory.abp import example_abp

ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

def parse_json(output):
    output=ANSI.sub('',output)
    decoder=json.JSONDecoder()
    for i,c in enumerate(output):
        if c=='{':
            try:value,_=decoder.raw_decode(output[i:])
            except ValueError:continue
            if isinstance(value,dict) and ('content' in value or 'results' in value):return value
    raise ValueError('No retrieval/search JSON in CLI output')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime',required=True);ap.add_argument('--semantic',action='store_true');args=ap.parse_args()
    runtime=Path(args.runtime).resolve();cli=runtime/'node_modules/.bin/ruflo'
    version=json.loads((runtime/'node_modules/ruflo/package.json').read_text())['version']
    if version!='3.56.10':raise ValueError('Expected Ruflo 3.56.10')
    evidence=Path(__file__).resolve().parents[1]/'evidence';evidence.mkdir(exist_ok=True)
    records=[];report={'ruflo_version':version,'status':'running','semantic_attempt':args.semantic,
        'runtime_lock_sha256':hashlib.sha256((runtime/'package-lock.json').read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    facts={'charging-window':'Project Kestrel electric fleet charging is permitted only between 01:00 and 04:00 UTC.',
           'retention-policy':'Project Kestrel encrypted checkpoints are retained for seven days; restored workspaces require separate deletion.'}
    with tempfile.TemporaryDirectory(prefix='ruflo-native-recall-') as tmp:
        root=Path(tmp);src=root/'source';src.mkdir();fresh=root/'fresh';fresh.mkdir()
        def run(cwd,*argv,required=True):
            start=time.monotonic()
            try:
                r=subprocess.run([str(cli),*argv],cwd=cwd,capture_output=True,text=True,timeout=60 if args.semantic else 30)
            except subprocess.TimeoutExpired as e:
                def decode(x):return x.decode(errors='replace') if isinstance(x,bytes) else (x or '')
                rec={'args':list(argv),'cwd':str(cwd),'timeout_seconds':e.timeout,
                     'stdout':decode(e.stdout),'stderr':decode(e.stderr)}
                records.append(json.loads(json.dumps(rec).replace(tmp,'<run>')))
                raise RuntimeError('CLI timeout during '+str(argv[:2])) from e
            rec={'args':list(argv),'cwd':str(cwd),'rc':r.returncode,'seconds':round(time.monotonic()-start,3),'stdout':r.stdout,'stderr':r.stderr}
            # Only synthetic test content is used; scrub ephemeral absolute paths.
            records.append(json.loads(json.dumps(rec).replace(tmp,'<run>')))
            if required and r.returncode:raise RuntimeError('Ruflo command failed: '+str(argv)+'\n'+r.stdout+'\n'+r.stderr)
            return r
        try:
            db=src/'.swarm/memory.db';db.parent.mkdir()
            common=['--path',str(db),'-n','recall-validation']
            for key,value in facts.items():run(src,'memory','store','-k',key,'--value',value,*common,'--provenance','tool_result',*(['--embedding','--vector'] if args.semantic else ['--no-embedding']))
            def retrieve(cwd,path,key,namespace='recall-validation',required=True):
                r=run(cwd,'memory','retrieve','-k',key,'-n',namespace,'--path',str(path),'--format','json',required=required)
                return parse_json(r.stdout) if required else r
            before={k:retrieve(src,db,k)['content'] for k in facts}
            assert before==facts,'Baseline exact recall differs'
            missing=retrieve(src,db,'missing-key',required=False);assert missing.returncode!=0
            wrong=retrieve(src,db,'charging-window',namespace='wrong-namespace',required=False);assert wrong.returncode!=0
            def search(cwd,path,kind,query,namespace='recall-validation'):
                r=run(cwd,'memory','search','-q',query,'-n',namespace,'--path',str(path),'--type',kind,'--format','json')
                return parse_json(r.stdout)
            keyword_before=search(src,db,'keyword','Kestrel')
            semantic_before=search(src,db,'semantic','When may the vehicles replenish their batteries?') if args.semantic else {'results':[], 'status':'not_attempted'}
            with contextlib.closing(sqlite3.connect(db)) as conn:
                embedding_rows=conn.execute('SELECT key,embedding_dimensions,embedding_model,embedding FROM memory_entries ORDER BY key').fetchall()
            embedding_evidence=[{'key':r[0],'dimensions':r[1],'model':r[2],'present':bool(r[3]),
                                 'sha256':hashlib.sha256(str(r[3]).encode()).hexdigest() if r[3] else None} for r in embedding_rows]
            dbs=[]
            for p in sorted(src.rglob('*.db')):
                try:
                    with contextlib.closing(sqlite3.connect(p)) as c:
                        tables=[row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                        rowcounts={t:c.execute('SELECT COUNT(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
                    dbs.append({'path':p.relative_to(src).as_posix(),'tables':rowcounts})
                except sqlite3.Error:pass
            report['database_layout']=dbs
            report['baseline_exact']=before
            # Prove a clean receiver does not already know the facts.
            empty=fresh/'.swarm/memory.db';empty.parent.mkdir()
            negative=retrieve(fresh,empty,'charging-window',required=False);assert negative.returncode!=0
            run(src,'daemon','stop',required=False)
            run(fresh,'daemon','stop',required=False)
            abp=example_abp('ruflo-memory');mandate=root/'memory.abp.json';mandate.write_text(json.dumps(abp));mandate.chmod(0o600)
            cfg={'principal':'local-agent','sources':{'ruflo-memory':str(db)},'abp_path':str(mandate),'store':str(root/'store'),'keys':str(root/'keys'),'restore_root':str(root/'restores')}
            config=root/'config.json';config.write_text(json.dumps(cfg));config.chmod(0o600)
            adapter=Adapter(config);cp=adapter.checkpoint('ruflo-memory')
            # Remove ALL original project DBs/indexes/config to prevent fallback reads.
            shutil.rmtree(src);src.mkdir()
            assert not db.exists()
            restored=adapter.restore(cp['id'],'receiver');outdb=Path(restored['workspace'])/'memory.sqlite'
            # Use the adapter's NEW workspace directly; never overwrite a live DB.
            fresh=Path(restored['workspace']);empty=outdb
            after={k:retrieve(fresh,empty,k)['content'] for k in facts};assert after==before
            missing_after=retrieve(fresh,empty,'missing-key',required=False);assert missing_after.returncode!=0
            wrong_after=retrieve(fresh,empty,'charging-window',namespace='wrong-namespace',required=False);assert wrong_after.returncode!=0
            keyword_after=search(fresh,empty,'keyword','Kestrel')
            semantic_after=search(fresh,empty,'semantic','When may the vehicles replenish their batteries?') if args.semantic else {'results':[], 'status':'not_attempted'}
            def keys(result):return sorted((r.get('namespace'),r.get('key')) for r in result['results'])
            assert keys(keyword_before)==keys(keyword_after) and len(keys(keyword_after))>=2
            assert keys(semantic_before)==keys(semantic_after)
            with contextlib.closing(sqlite3.connect(empty)) as conn:
                restored_embeddings=conn.execute('SELECT key,embedding_dimensions,embedding_model,embedding FROM memory_entries ORDER BY key').fetchall()
            assert restored_embeddings==embedding_rows
            semantic_gate=bool(args.semantic and all(r['present'] and r['dimensions'] and 'hash' not in str(r['model']).lower() for r in embedding_evidence)
                               and any(r.get('key')=='charging-window' for r in semantic_after['results']))
            report.update(status='partial' if args.semantic and not semantic_gate else 'passed',exact_recall={'before':before,'after':after,'equal':True},
                          negatives={'clean_receiver_missing':True,'unknown_key_rejected':True,'namespace_isolated':True},
                          keyword={'before':keys(keyword_before),'after':keys(keyword_after),'equal':True},
                          semantic={'before':semantic_before,'after':semantic_after,'result_keys_equal':True if args.semantic else None,'attempted':args.semantic,
                                    'quality_validated':semantic_gate,'embedding_evidence':embedding_evidence,'embedding_columns_unchanged':True,'stored_vector_count':sum(r['present'] for r in embedding_evidence),'status':'passed' if semantic_gate else ('blocked_no_stored_embeddings' if args.semantic and not any(r['present'] for r in embedding_evidence) else 'not_validated'),'gate_passed':semantic_gate,'note':'Search-path parity only; inspect backend/model evidence before claiming semantic quality.'},
                          database_layout=dbs,checkpoint=cp,source_project_removed=True)
        except BaseException as e:
            report.update(status='failed',error=str(e).replace(tmp,'<run>'));raise
        finally:
            for cwd in [src,fresh]:
                if cwd.exists():
                    try:run(cwd,'daemon','stop',required=False)
                    except Exception:pass
            (evidence/('ruflo-native-recall-semantic.json' if args.semantic else 'ruflo-native-recall.json')).write_text(json.dumps(report,indent=2)+'\n')
            (evidence/('ruflo-native-recall-semantic-trace.json' if args.semantic else 'ruflo-native-recall-trace.json')).write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'ruflo_version':version,'exact_recall':report['exact_recall']['equal'],
                      'keyword_recall':report['keyword']['equal'],'semantic_quality_validated':report['semantic']['quality_validated']},indent=2))

if __name__=='__main__':main()
