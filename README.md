# AgentArbiter

**On-chain dispute adjudication for AI-agent service agreements** — an
Intelligent Contract on [GenLayer](https://genlayer.com) that settles
"did the worker actually deliver?" disputes by validator consensus over
natural-language terms and live web evidence.

## Why this exists

The agent economy is getting payments (x402), identity (ERC-8004), and
interoperability (A2A) — but no dispute layer. When an AI agent hires
another agent (or a human) and the client says *"this doesn't meet the
spec"* while the worker says *"it does"*, there is no court to call. A
normal smart contract cannot help: the question is a judgment over
natural-language terms and off-chain evidence, not a computation.

AgentArbiter is that missing adjudication layer, built the GenLayer way:
the verdict is produced by a committee of validators, each of which
independently fetches the evidence and re-runs the judgment on its own
LLM, and is only stored when the committee agrees the verdicts are
equivalent under the contract's equivalence rules.

## What it does

```
create_agreement ──► assess_terms (optional, nondet #1)
      │                     scores how adjudicable the terms are
      ▼
open_dispute ──► submit_response ──► resolve_dispute (nondet #2)
 (claim +                            validators fetch both evidence
  evidence URL)                      pages, re-run the adjudication,
                                     agree on outcome + payment split
      │
      ├─ CLIENT_WINS  → worker share 0%
      ├─ WORKER_WINS  → worker share 100%
      ├─ SPLIT        → worker share = fulfilled fraction (basis points)
      └─ INCONCLUSIVE → no ruling; agreement reopens for better evidence
```

Two non-deterministic operations, two different equivalence designs:

1. **`assess_terms`** — a pre-flight "contract lint". An LLM scores how
   specific the agreement's terms are (deliverable, acceptance criteria,
   deadline, price) and lists what is missing. Most disputes are born as
   vague terms; this makes vagueness visible *before* work starts.
2. **`resolve_dispute`** — the adjudication itself. Both parties'
   statements and both evidence pages are evaluated against the terms,
   producing an outcome, a payment split, a confidence score, and a short
   reasoning (stored for transparency, never used for consensus).

## State design

All state lives in two `TreeMap[u256, …]` registries with monotonically
increasing IDs starting at 1 (existence checks are range checks against
the counters — no ambiguous map lookups).

**Agreement** (`@allow_storage` dataclass)

| Field | Type | Meaning |
|---|---|---|
| `client` | `Address` | Agreement creator; pays on acceptance |
| `worker` | `Address` | Service provider |
| `terms` | `str` | The natural-language terms — the "law" of the deal |
| `amount` | `u256` | Agreed amount (unit of account chosen by the parties) |
| `status` | `str` | `OPEN` → `DISPUTED` → `RESOLVED` / `CANCELLED`; `INCONCLUSIVE` verdicts return it to `OPEN` |
| `clarity_checked` | `bool` | Whether `assess_terms` has run |
| `clarity_score` | `u256` | 0–100 adjudicability score |
| `terms_clear` | `bool` | `clarity_score >= 70` |
| `clarity_notes` | `str` | Missing/vague elements found by the assessment |

**Dispute** (`@allow_storage` dataclass)

| Field | Type | Meaning |
|---|---|---|
| `agreement_id` | `u256` | Parent agreement |
| `claimant` / `respondent` | `Address` | Who opened the dispute / the other party |
| `claim` / `response` | `str` | Each side's statement |
| `claim_evidence_url` / `response_evidence_url` | `str` | Each side's public evidence page |
| `status` | `str` | `AWAITING_RESPONSE` → `READY` → `RESOLVED` / `INCONCLUSIVE` |
| `outcome` | `str` | `CLIENT_WINS` / `WORKER_WINS` / `SPLIT` / `INCONCLUSIVE` |
| `worker_share_bps` | `u256` | Worker's share of `amount`, basis points |
| `confidence` | `u256` | Committee-agreed confidence, 0–100 |
| `reasoning` | `str` | Leader's short justification (stored, never compared) |

Access control is deterministic and checked before any non-deterministic
work: only the two parties can open disputes, respond, assess, or resolve;
only the respondent can respond; only the client can cancel an `OPEN`
agreement; a dispute can be resolved exactly once, and only after both
sides have been heard.

## Validator / equivalence design

Both nondet operations use `gl.vm.run_nondet_unsafe` with a custom
validator — the pattern the GenLayer docs recommend for production
contracts. The validator **never trusts the leader**: it re-executes the
entire evaluation itself (its own `web.render` evidence fetches, its own
`exec_prompt` call) and compares only the *decision fields*:

| Field | Rule | Why |
|---|---|---|
| `outcome` | exact match | The verdict is the decision; anything less is not consensus |
| `is_clear` (clarity) | exact match | Gate check: a score tolerance must never flip "too vague" into "clear" |
| `worker_share_bps` | exact for decisive outcomes (pinned 0 / 10000 by construction); ±500 bps for `SPLIT` | Two honest evaluations of partial delivery rarely agree to the point |
| `clarity_score`, `confidence` | ±15 / ±20 | LLM scoring is subjective; the docs' numeric-tolerance pattern |
| `reasoning`, `missing` text | **not compared** | Wording differs between LLMs even when judgment is identical |

**Error classification** (docs taxonomy, via `gl.vm.UserError` prefixes):
`[EXPECTED]` business-rule failures and `[EXTERNAL]` evidence-fetch
failures agree only if the validator independently hits the same category
— so a dead evidence page becomes an agreed outcome instead of endless
leader rotation. `[LLM_ERROR]` (malformed/invalid LLM output) and VM
errors always disagree, forcing rotation to a fresh validator set.

**Prompt-injection defense:** evidence pages are untrusted input. The
adjudication prompt delimits all evidence as data and explicitly instructs
the model never to follow instructions contained in it; the LLM's output
is restricted to a strict JSON schema with an enumerated outcome, and
out-of-schema outcomes raise `[LLM_ERROR]` rather than being stored.

**Determinism hygiene:** storage is copied to memory before each nondet
block (nondet blocks cannot read storage); decisive outcomes pin the
share so stored state is a pure function of the agreed outcome; no
floats, no wall-clock reads, no forbidden imports (`os`/`time`/`random`).

## Scope — deliberate limits

- **No value custody.** The contract records the authoritative verdict
  (the settlement instruction: outcome + worker share of the agreed
  amount). It does not hold or move GEN. This keeps the submission
  focused on the adjudication logic — GenLayer's actual product — and
  avoids putting user funds behind un-audited code. The natural v2 is a
  `@gl.public.write.payable` funding step plus verdict-gated release via
  `gl` message emission, which the state machine already supports
  (`RESOLVED` + `worker_share_bps` is everything a release step needs).
- **No wall-clock deadlines.** The evidence window closes when the
  respondent answers; a non-responsive counterparty cannot be timed out
  yet. GenLayer exposes transaction datetime via `gl.message_raw`
  (used by production contracts such as VERDICT), so a response deadline
  is a contained v2 addition.
- **One evidence URL per side.** Multi-document evidence is a v2
  extension; the fetch/truncate path is already factored into
  `_fetch_evidence`.

## Run it

Prerequisites: Python 3.12+, Node.js (for the GenLayer CLI / Studio).

```bash
pip install genlayer-test genvm-linter

# 1. Lint (must be clean before any deploy)
genvm-lint check contracts/agent_arbiter.py

# 2. Direct-mode tests — in-process, mocked web + LLM, ~ms per test
pytest tests/direct/ -v

# 3a. Hosted Studio (no Docker): open https://studio.genlayer.com,
#     create a new contract file, paste contracts/agent_arbiter.py,
#     deploy, and drive the methods from the UI.
# 3b. Local Studio:
npm install -g genlayer
genlayer init
genlayer up            # Studio UI at http://localhost:8080

# 4. Integration smoke test (real consensus, real LLMs)
gltest tests/integration/ -v -s            # studionet (default)
```

### Try it in Studio (manual end-to-end)

1. Deploy `contracts/agent_arbiter.py`.
2. From account A, call `create_agreement` with account B's address, the
   sample terms from `tests/direct/test_agent_arbiter.py`, amount `1000`.
3. Call `assess_terms(1)` — wait for consensus; `get_agreement(1)` shows
   the clarity score.
4. From A, `open_dispute(1, "<claim>", "<public evidence URL>")`.
5. From B, `submit_response(1, "<response>", "<public evidence URL>")`.
6. From either, `resolve_dispute(1)`; after finalization,
   `get_dispute(1)` shows the committee's verdict.

## Repository layout

```
contracts/agent_arbiter.py                  the Intelligent Contract
tests/direct/test_agent_arbiter.py          18 direct-mode tests (mocked)
tests/integration/test_agent_arbiter_integration.py   Studio smoke test
gltest.config.yaml                          studionet / localnet config
README.md                                   this file
SUBMISSION.md                               portal submission checklist
```

## Sources relied on (checked 2026-11-17)

- GenLayer Docs — *Your First Contract* (header/dependency pinning,
  storage types): https://docs.genlayer.com/developers/intelligent-contracts/first-contract
- GenLayer Docs — *The Equivalence Principle* (leader/validator patterns,
  partial-field matching, numeric tolerance, gate checks, error
  classification): https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle
- GenLayer Docs — *Calling LLMs* (`exec_prompt`, `response_format="json"`,
  `gl.vm.Return` / `.calldata` validator convention, defensive parsing):
  https://docs.genlayer.com/developers/intelligent-contracts/features/calling-llms
- GenLayer Docs — *Testing Intelligent Contracts* (direct-mode fixtures
  `direct_vm` / `direct_deploy` / `direct_alice`…, `mock_web`, `mock_llm`,
  `expect_revert`): https://docs.genlayer.com/developers/intelligent-contracts/testing
- GenLayer Docs — full text (pinned runner hash
  `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`,
  `gl.message.sender_address`): https://docs.genlayer.com/full-documentation.txt
- Production patterns cross-checked against VERDICT (deployed Bradbury
  prediction-market contract, `run_nondet_unsafe` + exact field matching)
  and Beacon (release attestation; validators match on result + ordered
  obligation statuses, not explanations).

## Known uncertainties (honest list)

- The first line pins the exact GenVM runner hash published in the
  official docs as of 2026-11-17. If Studio offers a newer runner when
  deploying, update that one line — an unpinned/`latest` alias is
  rejected by the network.
- Some community references (e.g. the GenLayer dev skill) show an extra
  `# v0.1.0` first line and the `gl.vm.run_nondet(leader=…, validator=…)`
  kwargs form. This contract follows the current official docs instead:
  Depends-line first, `run_nondet_unsafe` positional form.
- Doc pages differ slightly on what the validator receives (a
  `gl.vm.Result` vs the raw value). The validator here handles both:
  `gl.vm.Return` (via `.calldata`), a raw `dict`, and `gl.vm.UserError`
  are each handled explicitly; anything else disagrees.
- This package was written and reviewed locally; it has **not** been
  deployed or executed yet. Run the lint + direct tests (step 1–2 above)
  before deploying, and treat any failure there as the source of truth.
