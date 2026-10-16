# SGit × rUv Memory — ABP-governed local MCP MVP

Version 0.2 connects **Agent Behaviour Policy → compiled Ruflo rules → enforced adapter operation → SGit encrypted checkpoint**. This is a local external MCP server, not native Ruflo plugin registration.

Requires Linux/macOS, Python 3.11+, Git and Node 24+. SGit is pinned to reviewed source commit `559752641bc520986fb0851b4a43875b6ad0d4ad` because its 0.22.3 version was unavailable from the package index. Tested on Linux/Python 3.12/Node 24.

## Install and reproduce

```bash
python -m venv .venv
. .venv/bin/activate
pip install .
python -m unittest discover -s tests -v
python demo.py
```

The real MCP stdio demo compiles a mandate, blocks an unauthorised namespace, checkpoints two synthetic SQLite facts, blocks approval-required deletion, removes the source DB, starts a new server process, restores both facts and rejects tampering. Recorded results are under `evidence/`. The tests also exercise live WAL writes and concurrent checkpoints.

## Define the mandate

Use `examples/memory.abp.json` as the starting point. It uses SGit's **ABP 0.1-poc document structure**, with the explicit adapter profile `sgit-ruv-memory/v1`. This is a narrow extension, not support for all upstream capabilities.

| Capability | Adapter action | Vocabulary |
|---|---|---|
| `write.memory.project` | `memory.checkpoint` | Adapter extension |
| `read.memory.project` | `memory.restore` | Adapter extension; permits read and isolated recovery |
| `read.record.history` | `memory.inspect` | Existing SGit primitive, mapped to checkpoint inspection |
| `delete.memory.project` | `memory.delete` | Adapter extension |

Each role has an `id`, `purpose` and capability `rows`. Each row supplies `reach`, `mandate`, `why` and explicit namespace `instances`. Deny and approval rows also require a `barrier`.

- `yes` compiles to `allow`; `no` to `deny`; `approval` to `require_approval`.
- Unsupported capabilities, versions, profiles, unknown fields, duplicate roles/capabilities, malformed values and wildcard/unknown namespaces reject the entire document. No silent skipping.
- Instances mean exact configured namespace identifiers, not arbitrary file paths or glob expressions. All effects retain that scope, including deny and approval.
- Unreachable capabilities cannot be granted. Unmatched requests default deny in Ruflo's evaluator.
- The ABP's owner and expiry are required. A date expires at 00:00 UTC at the start of that date; timezone-aware timestamps are also accepted by this profile.
- Approval-required actions are blocked. There is no human approval fulfilment mechanism yet.

The Python compiler adapts the structure and mandate/effect mapping of SGit's `poc/poc1-abp-to-ruflo-policy/compile.mjs`, with strict validation and the explicit mappings above. It is not a claim that SGit's existing 23-primitive compiler accepts these new memory primitives unchanged. The vocabulary extension is proposed for review in SGit PR #1.

## Configure and connect

Copy `examples/config.json` and `examples/memory.abp.json` into a private directory; edit absolute paths and review the mandate. Set both files to mode `0600`. `abp_path` resolves relative to the config file. Config supplies source allowlists and a fixed principal; that principal must match an ABP role. Raw `rules` and config-level expiry overrides are rejected, so they cannot bypass the mandate. Policy is compiled at server startup; restart after editing it. Expiry is checked on every operation.

Store, keys and restore_root directories are created with mode `0700`; existing directories must already use that mode. Keep keys separate from ciphertext. Identify the actual SQLite database used by your installed Ruflo commands before configuring it: layouts vary. A namespace authorises the **whole database**, not selected rows.

Example compatible MCP host configuration:

```json
{"mcpServers":{"sgit-ruv-memory":{
  "command":"/absolute/project/.venv/bin/sgit-ruv-memory",
  "env":{"SGIT_RUV_CONFIG":"/absolute/private/config.json"}
}}}
```

| Tool | Behaviour |
|---|---|
| `checkpoint(namespace)` | Policy check, consistent SQLite backup, integrity check, SGit vault init/commit, ciphertext publication |
| `inspect(checkpoint_id)` | Policy check, manifest metadata and ciphertext digest verification |
| `restore(checkpoint_id, workspace)` | Policy check, verify/decrypt/check SQLite, promote to a NEW workspace only |
| `close_run(checkpoint_id)` | Policy check, local checkpoint/key-record deletion; restored workspaces remain |

Each immutable checkpoint has its own SGit vault, not shared cross-checkpoint branch history. SGit's ref manager promotes the local snapshot commit to `current` for bare checkout; no remote push is performed. Only `.sg_vault/bare/` enters the durable ciphertext store. Private key records remain outside it. Temporary staging is removed on normal completion.

The encrypted manifest includes source ABP hash, compiled-rule hash, profile, owner, principal, database digest and creation time. Restore verifies that historical manifest; current authority still comes from the currently loaded ABP. These hashes bind evidence to a mandate; they are **not digital signatures** or immutable audit receipts.

## Verification and limits

16 tests cover compiler mappings, scoped effects, invalid-policy rejection, digest binding, deny/approval behaviour, identity mismatch, raw-rule bypass rejection, wrong keys, tampering, expiry, live WAL writers, concurrent checkpoints, roundtrip and scoped deletion. The real MCP demo passes separately. Validation records name the exact SGit source and adapter hashes.

This is an external adapter using a pinned copy of Ruflo's evaluator, not Ruflo's running policy state. Only adapter tools pass through this gate. Other shell/network tools are unaffected. The host, local config and private key records are trusted; owner/role strings are not authenticated signatures. Separate processes/configurations are needed for separate host principals.

SQLite backup is consistent for one DB, not multiple databases or external vector files. Ruflo CLI semantic recall and database compatibility are still unverified against the synthetic fixture. RVF, remote sync, Federation announcements, a full ABP compiler, native plugin registration, key rotation/HSM and multi-tenant isolation remain follow-ups.

Plaintext exists during staging and intentionally in restored workspaces. Local deletion does not erase source DBs, restored copies, external keys, OS caches or backups. A plaintext-fragment probe is not a cryptographic audit. Atomic renames protect normal execution, not power-loss durability or crash-orphan cleanup.

The original 64-second video demonstrates the pre-ABP seven-test baseline. The updated [video script](https://github.com/mondweep/sgit-ruv-memory/blob/main/media/render_video.py) can render the latest evidence with original synthesized music; the SGit POC copy does not bundle media files.

## Attribution

- SGit CLI source: https://github.com/SGit-AI/SGit-AI__CLI , pinned commit above, Apache-2.0.
- ABP structure/compiler inspiration: https://github.com/SGit-AI/SGit-AI__Website__Ruv at `d9b9ab30542211e8f87c51bf24f05d942d555f2a`, Apache-2.0. See `NOTICE`.
- Ruflo evaluator: https://github.com/ruvnet/ruflo at `1882006a02487590c8c66a7eec8d7504f6af33c3`, MIT, by rUv/ruvnet. Vendored files retain MIT license; only evaluator import extension is changed for Node type stripping.

Adapter code is MIT; upstream components retain their licenses.
