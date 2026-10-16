"""Local trusted-host adapter. Store and keys must be separate private directories."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from sgit_ai.core.Vault__Sync import Vault__Sync
from sgit_ai.core.Vault__Bare import Vault__Bare
from .abp import compile_abp


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_digest(path):
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlinks forbidden')
        if p.is_file():
            h.update(json.dumps([p.relative_to(path).as_posix(), digest(p)]).encode())
    return h.hexdigest()


class Adapter:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        if self.config_path.stat().st_mode & 0o022:
            raise ValueError('Config must not be group/world writable')
        self.cfg = json.loads(self.config_path.read_text())
        if 'rules' in self.cfg or 'valid_until' in self.cfg:
            raise ValueError('Use abp_path; raw rules/expiry overrides are forbidden')
        policy_path = (self.config_path.parent / self.cfg['abp_path']).resolve(strict=True)
        if policy_path.stat().st_mode & 0o022:
            raise ValueError('ABP must not be group/world writable')
        self.policy = compile_abp(json.loads(policy_path.read_text()), set(self.cfg['sources']))
        self.principal = self.cfg['principal']
        if self.principal not in self.policy['roles']:
            raise ValueError('Host principal must match an ABP role')
        if self.policy['expires'] <= dt.datetime.now(dt.timezone.utc):
            raise PermissionError('ABP mandate expired')
        self.rules = self.policy['rules']
        self.policy_digest = self.policy['rules_sha256']
        self.store = Path(self.cfg['store']).resolve()
        self.keys = Path(self.cfg['keys']).resolve()
        self.restore_root = Path(self.cfg['restore_root']).resolve()
        if self.store == self.keys or self.store in self.keys.parents or self.keys in self.store.parents:
            raise ValueError('Keys and store must be separate')
        for p in (self.store, self.keys, self.restore_root):
            p.mkdir(parents=True, exist_ok=True, mode=0o700)
            if p.stat().st_mode & 0o077:
                raise ValueError('Adapter directories must have mode 0700')

    def gate(self, action, namespace):
        expiry = self.policy['expires']
        if expiry <= dt.datetime.now(dt.timezone.utc):
            raise PermissionError('Mandate expired')
        req = {'identity': {'id': self.principal, 'type': 'agent'}, 'action': {'type': action, 'resource': namespace}}
        bridge = Path(__file__).parent / 'policy' / 'bridge.mjs'
        result = subprocess.run(['node', str(bridge)], input=json.dumps({'request': req, 'rules': self.rules}),
                                text=True, capture_output=True, timeout=10, check=True)
        decision = json.loads(result.stdout)
        if decision['enforcedOutcome'] != 'allowed':
            raise PermissionError('Policy blocked operation: ' + decision['reason'])
        return decision

    @contextlib.contextmanager
    def lock(self):
        with open(self.keys / '.lock', 'a') as f:
            os.chmod(f.name, 0o600)
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def record(self, checkpoint_id):
        if not re.fullmatch(r'[0-9a-f]{32}', checkpoint_id):
            raise ValueError('Invalid checkpoint ID')
        return self.keys / (checkpoint_id + '.json')

    def checkpoint(self, namespace):
        self.gate('memory.checkpoint', namespace)
        source = Path(self.cfg['sources'][namespace]).resolve(strict=True)
        if not source.is_file():
            raise ValueError('Source must be a SQLite file')
        with self.lock(), tempfile.TemporaryDirectory(dir=self.keys) as tmp:
            work = Path(tmp) / 'vault'
            work.mkdir(mode=0o700)
            db = work / 'memory.sqlite'
            with contextlib.closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as src:
                with contextlib.closing(sqlite3.connect(db)) as dest:
                    # Deadline prevents endless waiting under sustained contention.
                    import time
                    deadline = time.monotonic() + 30
                    def progress(*_):
                        if time.monotonic() > deadline:
                            raise TimeoutError('Snapshot deadline exceeded')
                    src.backup(dest, pages=256, progress=progress)
                    if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Invalid SQLite snapshot')
            cid = uuid.uuid4().hex
            manifest = {'schema': 1, 'id': cid, 'namespace': namespace, 'principal': self.principal,
                        'created_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'backend': 'sqlite-backup',
                        'database_sha256': digest(db), 'policy_sha256': self.policy_digest,
                        'sgit_version': '0.22.3', 'abp_sha256': self.policy['abp_sha256'],
                        'abp_profile': self.policy['profile'], 'abp_owner': self.policy['owner']}
            (work / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
            sync = Vault__Sync()
            init = sync.init(str(work), allow_nonempty=True)
            commit = sync.commit(str(work), message='memory checkpoint')
            # Local commits advance the clone branch; bare checkout resolves named current.
            # Promote this single-writer checkpoint to current without a network push.
            from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
            keys = sync.crypto.derive_keys_from_vault_key(init['vault_key'])
            Vault__Ref_Manager(vault_path=str(work / '.sg_vault'), crypto=sync.crypto).write_ref(
                keys['ref_file_id'], str(commit['commit_id']), keys['read_key_bytes'])
            # Only SGit's bare encrypted store leaves private staging. Never local/ or keys.
            bare = work / '.sg_vault' / 'bare'
            seal = tree_digest(bare)
            staging = self.store / ('.' + cid)
            target = self.store / cid
            try:
                shutil.copytree(bare, staging)
                staging.rename(target)
                rec = {'vault_key': init['vault_key'], 'manifest': manifest, 'bare_sha256': seal,
                       'commit_id': str(commit.get('commit_id', ''))}
                record = self.record(cid)
                fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as f:
                    json.dump(rec, f)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                shutil.rmtree(target, ignore_errors=True)
                raise
            return {**manifest, 'ciphertext_sha256': seal, 'status': 'checkpointed'}

    def inspect(self, checkpoint_id):
        rec = json.loads(self.record(checkpoint_id).read_text())
        self.gate('memory.inspect', rec['manifest']['namespace'])
        return {**rec['manifest'], 'verified': tree_digest(self.store / checkpoint_id) == rec['bare_sha256']}

    def restore(self, checkpoint_id, workspace):
        rec = json.loads(self.record(checkpoint_id).read_text())
        self.gate('memory.restore', rec['manifest']['namespace'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', workspace):
            raise ValueError('Invalid workspace name')
        with self.lock():
            target = self.restore_root / workspace
            if target.exists():
                raise FileExistsError('Restore never overwrites an existing workspace')
            if tree_digest(self.store / checkpoint_id) != rec['bare_sha256']:
                raise ValueError('Checkpoint ciphertext integrity mismatch')
            with tempfile.TemporaryDirectory(dir=self.keys) as tmp:
                work = Path(tmp) / 'vault'
                (work / '.sg_vault').mkdir(parents=True)
                shutil.copytree(self.store / checkpoint_id, work / '.sg_vault' / 'bare')
                Vault__Bare().checkout(str(work), rec['vault_key'])
                manifest = json.loads((work / 'manifest.json').read_text())
                if manifest != rec['manifest'] or digest(work / 'memory.sqlite') != manifest['database_sha256']:
                    raise ValueError('Snapshot manifest verification failed')
                with contextlib.closing(sqlite3.connect(work / 'memory.sqlite')) as db:
                    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Invalid database')
                stage = Path(tempfile.mkdtemp(prefix='.restore-', dir=self.restore_root))
                try:
                    shutil.copy2(work / 'memory.sqlite', stage / 'memory.sqlite')
                    shutil.copy2(work / 'manifest.json', stage / 'manifest.json')
                    stage.rename(target)
                except BaseException:
                    shutil.rmtree(stage, ignore_errors=True)
                    raise
            return {'status': 'restored', 'workspace': str(target), 'database_sha256': manifest['database_sha256']}

    def close_run(self, checkpoint_id):
        rec = json.loads(self.record(checkpoint_id).read_text())
        self.gate('memory.delete', rec['manifest']['namespace'])
        with self.lock():
            shutil.rmtree(self.store / checkpoint_id)
            self.record(checkpoint_id).unlink()
        return {'status': 'deleted', 'scope': 'local checkpoint and adapter key record only',
                'retained': 'Restored workspaces and external backups are not erased'}
