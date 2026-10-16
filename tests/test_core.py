import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from sgit_ruv_memory.core import Adapter
from sgit_ruv_memory.abp import example_abp

class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'source.sqlite'
        with sqlite3.connect(self.db) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE facts(key TEXT PRIMARY KEY,value TEXT)')
            db.executemany('INSERT INTO facts VALUES (?,?)',[('coder','Use SQLite backup for a consistent checkpoint'),('tester','Verify restored memory before promotion')])
        self.cfg={'store':str(self.root/'store'),'keys':str(self.root/'keys'),'restore_root':str(self.root/'restored'),
                  'principal':'local-agent','sources':{'demo':str(self.db)},'abp_path':'mandate.json'}
        self.abp=example_abp();self.abp_path=self.root/'mandate.json'
        self.abp_path.write_text(json.dumps(self.abp));self.abp_path.chmod(0o600)
        self.path=self.root/'config.json';self.path.write_text(json.dumps(self.cfg));self.path.chmod(0o600)
        self.a=Adapter(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_roundtrip_and_no_plaintext(self):
        c=self.a.checkpoint('demo');self.db.unlink();r=self.a.restore(c['id'],'fresh')
        with sqlite3.connect(Path(r['workspace'])/'memory.sqlite') as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM facts').fetchone()[0],2)
        self.assertTrue(self.a.inspect(c['id'])['verified'])
        for f in (self.a.store/c['id']).rglob('*'):
            if f.is_file():
                self.assertNotIn(b'Use SQLite backup',f.read_bytes());self.assertNotIn(b'sgit_private_vault_',f.read_bytes())
        with self.assertRaises(FileExistsError):self.a.restore(c['id'],'fresh')
    def test_policy_denies_before_side_effect(self):
        with self.assertRaises(PermissionError):self.a.checkpoint('forbidden')
        self.assertEqual(list(self.a.store.iterdir()),[])
    def test_tampering_rejected_without_workspace(self):
        c=self.a.checkpoint('demo');f=next(p for p in (self.a.store/c['id']).rglob('*') if p.is_file());f.write_bytes(f.read_bytes()+b'X')
        with self.assertRaises(ValueError):self.a.restore(c['id'],'bad')
        self.assertFalse((self.a.restore_root/'bad').exists())
    def test_wrong_key_and_path_escape(self):
        c=self.a.checkpoint('demo');p=self.a.record(c['id']);r=json.loads(p.read_text());r['vault_key']='wrongpass:abcdefgh';p.write_text(json.dumps(r))
        with self.assertRaises(Exception):self.a.restore(c['id'],'wrong')
        self.assertFalse((self.a.restore_root/'wrong').exists())
        with self.assertRaises(ValueError):self.a.restore(c['id'],'../escape')
    def test_concurrent_checkpoints_and_delete(self):
        with ThreadPoolExecutor(2) as ex:cs=list(ex.map(lambda _:self.a.checkpoint('demo'),range(2)))
        self.assertNotEqual(cs[0]['id'],cs[1]['id'])
        for c in cs:self.assertTrue(self.a.inspect(c['id'])['verified'])
        self.a.close_run(cs[0]['id']);self.assertFalse(self.a.record(cs[0]['id']).exists())
    def test_live_wal_writer_snapshot_is_consistent(self):
        import threading
        stop=threading.Event()
        def writer():
            with sqlite3.connect(self.db) as db:
                while not stop.is_set():
                    db.execute("UPDATE facts SET value=value || '.' WHERE key='coder'")
                    db.commit()
        t=threading.Thread(target=writer);t.start()
        try:
            c=self.a.checkpoint('demo')
        finally:
            stop.set();t.join(timeout=5)
        r=self.a.restore(c['id'],'live')
        with sqlite3.connect(Path(r['workspace'])/'memory.sqlite') as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM facts').fetchone()[0],2)

    def test_expired_and_approval_fail_closed(self):
        self.abp['valid_until']='2000-01-01T00:00:00+00:00';self.abp_path.write_text(json.dumps(self.abp))
        with self.assertRaises(PermissionError):Adapter(self.path)
        self.abp['valid_until']='2027-01-01T00:00:00+00:00'
        self.abp['roles'][0]['rows'][0].update(mandate='approval',barrier='human must approve')
        self.abp_path.write_text(json.dumps(self.abp))
        with self.assertRaises(PermissionError):Adapter(self.path).checkpoint('demo')

    def test_abp_deny_restore_and_delete_have_no_side_effects(self):
        c=self.a.checkpoint('demo')
        for row in self.abp['roles'][0]['rows']:
            if row['capability'] in ('read.memory.project','delete.memory.project'):
                row.update(mandate='no',barrier='operator retains checkpoint')
        self.abp_path.write_text(json.dumps(self.abp));a=Adapter(self.path)
        with self.assertRaises(PermissionError):a.restore(c['id'],'denied')
        with self.assertRaises(PermissionError):a.close_run(c['id'])
        self.assertFalse((a.restore_root/'denied').exists())
        self.assertTrue(a.record(c['id']).exists())
        self.assertTrue((a.store/c['id']).exists())

    def test_abp_manifest_binds_source_and_rules(self):
        c=self.a.checkpoint('demo')
        self.assertEqual(c['abp_sha256'],self.a.policy['abp_sha256'])
        self.assertEqual(c['policy_sha256'],self.a.policy['rules_sha256'])
        self.assertEqual(self.a.inspect(c['id'])['abp_sha256'],c['abp_sha256'])

    def test_raw_rules_cannot_bypass_abp(self):
        self.cfg['rules']=[{'effect':'allow','actions':['*']}]
        self.path.write_text(json.dumps(self.cfg))
        with self.assertRaises(ValueError):Adapter(self.path)

    def test_unknown_role_rejected(self):
        self.cfg['principal']='impersonated'
        self.path.write_text(json.dumps(self.cfg))
        with self.assertRaises(ValueError):Adapter(self.path)

    def test_scoped_deny_does_not_widen_and_approval_blocks_all_tools(self):
        self.cfg['sources']['other']=str(self.db)
        self.path.write_text(json.dumps(self.cfg))
        role=self.abp['roles'][0]
        for row in role['rows']:
            row.update(mandate='no',barrier='restricted demo')
        self.abp_path.write_text(json.dumps(self.abp));a=Adapter(self.path)
        for action in ['memory.checkpoint','memory.inspect','memory.restore','memory.delete']:
            with self.subTest(action=action),self.assertRaises(PermissionError):a.gate(action,'demo')
        # Second role has authority on other only; scoped denial for local-agent cannot spill.
        import copy
        second=copy.deepcopy(role);second['id']='other-agent'
        for row in second['rows']:row.update(mandate='yes',instances=['other'])
        self.abp['roles'].append(second);self.abp_path.write_text(json.dumps(self.abp))
        self.cfg['principal']='other-agent';self.path.write_text(json.dumps(self.cfg));a=Adapter(self.path)
        self.assertEqual(a.gate('memory.checkpoint','other')['enforcedOutcome'],'allowed')
        for row in second['rows']:row.update(mandate='approval',barrier='human approval')
        self.abp_path.write_text(json.dumps(self.abp));a=Adapter(self.path)
        for action in ['memory.checkpoint','memory.inspect','memory.restore','memory.delete']:
            with self.subTest(action=action),self.assertRaises(PermissionError):a.gate(action,'other')

if __name__=='__main__':unittest.main()
