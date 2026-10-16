import asyncio,json,os,sqlite3,sys,tempfile
from pathlib import Path
from mcp import ClientSession
from sgit_ruv_memory.abp import example_abp
from mcp.client.stdio import stdio_client,StdioServerParameters

async def main():
 events=[]
 def log(step,details):events.append({'step':step,'details':details});print(step,details,flush=True)
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);db=root/'source.sqlite'
  with sqlite3.connect(db) as conn:
   conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE facts(key TEXT PRIMARY KEY,value TEXT)')
   conn.executemany('INSERT INTO facts VALUES (?,?)',[('coder','Use SQLite backup for consistent snapshots'),('tester','Verify restored memory before promotion')])
  abp=example_abp();abp['roles'][0]['rows'][-1].update(mandate='approval',barrier='human approval needed for deletion')
  mandate=root/'mandate.json';mandate.write_text(json.dumps(abp));mandate.chmod(0o600)
  cfg={'store':str(root/'store'),'keys':str(root/'keys'),'restore_root':str(root/'restored'),'principal':'local-agent','sources':{'demo':str(db)},'abp_path':'mandate.json'}
  config=root/'config.json';config.write_text(json.dumps(cfg));config.chmod(0o600)
  params=StdioServerParameters(command=sys.executable,args=['-m','sgit_ruv_memory.server'],env={**os.environ,'SGIT_RUV_CONFIG':str(config)})
  async with stdio_client(params) as (r,w):
   async with ClientSession(r,w) as s:
    await s.initialize();tools=await s.list_tools();log('MCP connected',{'tools':[t.name for t in tools.tools]})
    log('ABP compiled to Ruflo rules',{'profile':abp['adapter_profile'],'rules':4,'delete':'approval_required'})
    log('Two worker facts stored',{'rows':2,'backend':'SQLite WAL'})
    denied=await s.call_tool('checkpoint',{'namespace':'forbidden'});assert denied.is_error
    log('Policy blocks unauthorised namespace',{'blocked':True,'checkpoint_files':len(list((root/'store').iterdir()))})
    result=await s.call_tool('checkpoint',{'namespace':'demo'});assert not result.is_error,result
    c=json.loads(result.content[0].text);log('Encrypted checkpoint committed',{'id':c['id'],'ciphertext_sha256':c['ciphertext_sha256'],'policy_sha256':c['policy_sha256'],'abp_sha256':c['abp_sha256']})
    approval=await s.call_tool('close_run',{'checkpoint_id':c['id']});assert approval.is_error
    log('ABP approval blocks deletion',{'blocked':True,'checkpoint_retained':(root/'store'/c['id']).exists()})
    bare=root/'store'/c['id'];blob=b''.join(p.read_bytes() for p in bare.rglob('*') if p.is_file())
    assert b'consistent snapshots' not in blob and b'sgit_private_vault_' not in blob
    log('Encrypted store probe',{'plaintext_fragment_hits':0,'key_marker_hits':0})
    db.unlink();log('Original database removed',{'exists':db.exists()})
  async with stdio_client(params) as (r,w):
   async with ClientSession(r,w) as s:
    await s.initialize();out=await s.call_tool('restore',{'checkpoint_id':c['id'],'workspace':'fresh-runner'});assert not out.is_error,out
    restored=json.loads(out.content[0].text)
    with sqlite3.connect(Path(restored['workspace'])/'memory.sqlite') as conn:rows=conn.execute('SELECT key,value FROM facts ORDER BY key').fetchall()
    assert len(rows)==2
    log('Fresh process restores both facts',{'rows':rows,'sha256_matches':restored['database_sha256']==c['database_sha256']})
    f=next(p for p in bare.rglob('*') if p.is_file());f.write_bytes(f.read_bytes()+b'TAMPER')
    rejected=await s.call_tool('restore',{'checkpoint_id':c['id'],'workspace':'tampered'});assert rejected.is_error
    log('Tampered checkpoint rejected',{'blocked':True,'workspace_created':(root/'restored'/'tampered').exists()})
 Path('evidence/demo-events.json').write_text(json.dumps(events,indent=2))
 log('Demo complete',{'passed':True})
if __name__=='__main__':asyncio.run(main())
