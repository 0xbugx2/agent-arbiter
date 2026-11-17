"""Studio-mode smoke test for AgentArbiter.

Deploys the contract to a real GenLayer environment (default: studionet,
see gltest.config.yaml) and exercises it with REAL validator consensus and
REAL LLM calls. Because adjudication is genuinely non-deterministic, this
test asserts state-machine outcomes (transactions succeed; stored values
are sane), never a specific verdict.

Covered here with a single funded account:
  deploy -> create_agreement (worker = a distinct named address; naming a
  worker does not require the worker's signature) -> assess_terms (real
  LLM consensus) -> read views back.

The full two-party dispute flow needs the worker's key to call
submit_response. Drive it manually in GenLayer Studio (see README,
"Try it in Studio") or extend this file with a second configured account.

Run:
    pip install genlayer-test
    gltest tests/integration/ -v -s                      # studionet
    gltest tests/integration/ -v -s --network localnet   # local Studio
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

TERMS = (
    "Build a landing page for the client's coffee shop. Deliverable: a "
    "single-page website with a menu, prices, and a contact form. "
    "Acceptance criteria: the page loads and lists at least 10 items with "
    "prices. Deadline: 2026-12-01. Price: 1000 GEN, paid on acceptance."
)

# Any address distinct from the deployer; replace with a real second
# account's address for the full dispute flow.
WORKER_ADDRESS = "0x0000000000000000000000000000000000000002"


def test_deploy_create_and_assess_on_studio():
    factory = get_contract_factory("AgentArbiter")
    contract = factory.deploy(args=[])

    create_tx = contract.create_agreement(
        args=[WORKER_ADDRESS, TERMS, 1000]
    ).transact()
    assert tx_execution_succeeded(create_tx)

    assert contract.get_agreement_count(args=[]).call() == 1

    agreement = json.loads(contract.get_agreement(args=[1]).call())
    assert agreement["status"] == "OPEN"
    assert agreement["amount"] == 1000

    # Real non-deterministic consensus: validators run the clarity prompt
    # on their own LLMs. We only assert the assessment was recorded.
    assess_tx = contract.assess_terms(args=[1]).transact()
    assert tx_execution_succeeded(assess_tx)

    agreement = json.loads(contract.get_agreement(args=[1]).call())
    assert agreement["clarity_checked"] is True
    assert 0 <= agreement["clarity_score"] <= 100
