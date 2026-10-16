# SGit × rUv Memory — local MVP

A working stdio MCP server for policy-gated, encrypted SQLite checkpoints and isolated restore. Uses SGit 0.22.3 source pinned to Git commit `559752641bc520986fb0851b4a43875b6ad0d4ad` (not an assumed PyPI release), and its actual vault init/commit/checkout implementation and a pinned copy of Ruflo's policy evaluator in enforce mode. Linux/macOS, Python 3.11+, Node 24+ required. Tested on Linux, Python 3.12, Node 24.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install .
python -m unittest discover -s tests -v
python demo.py
```

`demo.py` uses a real MCP client and two fresh server processes. It creates its own synthetic SQLite memory fixture and temporary configuration, checkpoints two role-labelled facts, removes the source database, restores and queries both rows, and rejects tampered ciphertext. It writes non-secret evidence under `evidence/`. Run it from this project directory.

## Connect your own memory database

Create `config.json` outside your code repository, with mode 0600. Use absolute paths. The adapter creates store, keys and restore_root directories with mode 0700; existing directories must already have those permissions. Keys must be separate from store. Sources are host-allowlisted SQLite files; callers cannot choose filesystem paths or impersonate another principal.

```json
{
  "store": "/absolute/private/checkpoints",
  "keys": "/absolute/private/key-records",
  "restore_root": "/absolute/private/restored",
  "principal": "local-agent",
  "valid_until": "2027-01-01T00:00:00+00:00",
  "sources": {"project": "/absolute/project/.swarm/memory.db"},
  "rules": [{
    "id": "project-memory",
    "effect": "allow",
    "actions": ["memory.checkpoint", "memory.inspect", "memory.restore"],
    "principals": ["local-agent"],
    "resources": ["project"]
  }]
}
```

Confirm which database your installed Ruflo version actually uses before configuring it. No Ruflo CLI schema or semantic search compatibility is claimed from the synthetic fixture. The adapter copies an entire database, not selected rows; do not map different security domains in one database to separate namespaces.

Example MCP host configuration (substitute your paths):

```json
{"mcpServers":{"sgit-ruv-memory":{
  "command":"/absolute/project/.venv/bin/sgit-ruv-memory",
  "env":{"SGIT_RUV_CONFIG":"/absolute/private/config.json"}
}}}
```

Tools:
- `checkpoint(namespace)` — SQLite backup, integrity check, encrypted SGit commit, local ciphertext publication.
- `inspect(checkpoint_id)` — compare store digest with trusted private record.
- `restore(checkpoint_id, workspace)` — verify, decrypt, check manifest/database, atomically rename into a NEW workspace.
- `close_run(checkpoint_id)` — delete local encrypted checkpoint and its private key record; requires explicit `memory.delete` permission.

No approval bypass exists: `require_approval` is blocked in this version. An approval UX is deferred. Unknown operations default deny. The principal is the host-configured server identity, not independently authenticated per caller. Use separate processes/configurations for separate principals. The adapter gates its own tools only, not arbitrary host shell/network actions.

## What is stored

One independent SGit vault per immutable checkpoint, with an initial commit and snapshot commit. This deliberately avoids binary database merges; it is not a shared multi-worker vault or cross-checkpoint Git history. Each encrypted vault contains `memory.sqlite` and `manifest.json`; private staging is removed afterward. Local commits normally advance SGit's clone branch, so the adapter uses SGit's ref manager to promote the snapshot commit to `current` before bare checkout. No network push is performed.

The durable store receives only `.sg_vault/bare/`. Vault keys, manifests and trusted ciphertext digests are retained in separate private key records. The manifest binds the database digest, policy digest, namespace, principal and time. It is digest-bound, not independently signed. Local OS access is the trust boundary: a process that can alter both keys and store can forge the checkpoint. SGit encrypts with its upstream cryptography; this adapter introduces no cipher.

SQLite backup is consistent for one database. It does not guarantee a common transaction across multiple databases, external vector files, or an entire Ruflo project. It preserves SQLite schema/data and verifies `PRAGMA integrity_check`. Restore does not overwrite existing workspaces. Temporary plaintext exists during checkpoint/restore, and restored workspaces intentionally contain plaintext.

## Verification

Seven tests cover roundtrip, leak probes, wrong keys, tampering, policy denial before side effects, expiry, approval-required denial, namespace/path restrictions, concurrent checkpoints, local deletion and a live WAL writer. A real MCP transport demonstration runs in addition to these tests. Evidence is in `evidence/tests.txt`, `evidence/demo-run.txt` and `evidence/demo-events.json`.

The [video-generation script](https://github.com/mondweep/sgit-ruv-memory/blob/main/media/render_video.py) is maintained in the standalone repository. The video is an animated walkthrough of that recorded MCP run, not a screen capture of Ruflo or a claim of full end-to-end Ruflo semantic recall. Its captions and digest come from the saved demo evidence. Music is an original synthesized instrumental generated by `media/render_video.py`; no voiceover or third-party music recording.

## Deliberate limits and next steps

- Local only: no SGit remote server, Federation publish or cloud deployment.
- SQLite only: RVF integration and Ruflo CLI retrieval tests remain next steps.
- No digital signatures/ABP grammar compiler or human approval interface yet. Rules directly use Ruflo's evaluator schema.
- No multi-tenant isolation, key rotation, HSM, secure erase or backup erasure guarantee.
- The store leaks sizes, file counts and access times. A fragment probe is not a cryptographic audit.
- Local deletion does not remove restored workspaces, source databases, OS caches or backups.
- Process locking serializes checkpoint/restore/delete; snapshot work is bounded by a 30-second backup deadline. Atomic renames protect normal execution, but power-loss durability and crash-orphan reconciliation are not implemented.
- Review large database performance, retention and key custody before a production deployment.

## Upstream provenance

- SGit CLI: https://github.com/SGit-AI/SGit-AI__CLI at `559752641bc520986fb0851b4a43875b6ad0d4ad`, Apache-2.0 (installed as dependency, not bundled).
- Ruflo: https://github.com/ruvnet/ruflo at `1882006a02487590c8c66a7eec8d7504f6af33c3`, MIT. Vendored evaluator.ts, envelope.ts and types.ts; only local import extension changed from .js to .ts for Node type stripping. See vendor/ruflo/LICENSE and policy/LICENSE.
- Initial inspiration: https://github.com/SGit-AI/SGit-AI__Website__Ruv .

Adapter code and generated original music: MIT; upstream components retain their respective licenses.
