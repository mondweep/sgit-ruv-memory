# Ruflo-native recall validation

Pinned CLI: `ruflo@3.56.10`. Runtime installed with lifecycle scripts enabled; native better-sqlite3 is present. `scripts/validate_ruflo_recall.py` records the runtime lock hash and runner hash.

| Gate | Outcome |
|---|---|
| Store two facts using Ruflo CLI | PASS |
| Retrieve exact values using Ruflo before backup | PASS |
| Unknown-key and wrong-namespace controls | PASS |
| Clean negative-control project lacks the facts | PASS |
| ABP-governed encrypted checkpoint of actual `.swarm/memory.db` | PASS |
| Remove entire original project | PASS |
| Retrieve both values using Ruflo in a new restored workspace | PASS |
| Keyword result keys agree before/after | PASS |
| Restore embedding-column contents unchanged | PASS, but both are empty |
| Embedding-based semantic recall | NOT VALIDATED: no stored vectors and empty paraphrase results |

The embedding-enabled run explicitly passes `--embedding --vector`. ONNX loading messages appear, but CLI output reports Vector No, the two SQLite rows have null embedding dimensions and no embedding payload, and the semantic query returns zero results before and after recovery. That is not a semantic success or evidence that the adapter lost vectors; the source contained none. `status: partial` in the semantic report means exact/keyword recovery passed but the semantic gate did not.

The initial failed recovery test and transcript are retained. That test copied the snapshot over a DB already opened by a negative-control run. The corrected runner uses the adapter's new workspace directly and never overwrites an opened database. This required a test-procedure correction, not a change to adapter checkpoint/restore code.

The baseline runner uses `--no-embedding`; the separate semantic experiment uses explicit embedding flags. Exact-key recovery is proven for one real Ruflo SQLite memory path and two CLI-written facts, not all Ruflo stores, RVF, project-wide state or production workloads. The next investigation is why this pinned CLI/backend combination did not persist embeddings, then a nonempty semantic recall test with relevant and unrelated controls.
