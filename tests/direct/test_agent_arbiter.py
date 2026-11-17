"""Direct-mode tests for AgentArbiter (contracts/agent_arbiter.py).

Runs fully in-process with the GenLayer Testing Suite — no Studio, no
network. Web fetches and LLM calls are mocked; the same mocks serve both
the leader and the validator path, so consensus agreement is exercised
with identical independent evaluations. Validator *disagreement* paths
(different LLM answers per role) cannot be expressed with regex mocks in
direct mode; they are covered by the Studio integration smoke test and by
the equivalence unit logic documented in the contract.

Run:
    pip install genlayer-test genvm-linter
    genvm-lint check contracts/agent_arbiter.py
    pytest tests/direct/ -v
"""

import json

CONTRACT_PATH = "contracts/agent_arbiter.py"

TERMS = (
    "Build a landing page for the client's coffee shop. Deliverable: a "
    "single-page website with a menu, prices, and a contact form, published "
    "at the URL given as evidence. Acceptance criteria: the page loads, the "
    "menu lists at least 10 items with prices, and the contact form sends an "
    "email. Deadline: 2026-12-01. Price: 1000 GEN, paid on acceptance."
)

VAGUE_TERMS = "Do some marketing stuff for us and make it good, thanks."

CLAIM = (
    "The worker delivered the page two weeks late and the contact form does "
    "not send anything. The work does not meet the acceptance criteria."
)
RESPONSE = (
    "The page is live at the evidence URL with the full menu and prices. "
    "The contact form works; the client's mail server rejected the test "
    "message, which is outside my deliverable."
)

EVIDENCE_URL = "https://evidence.example.com/deliverable"
EVIDENCE_BODY = (
    "Sunny Cup Coffee — Menu: Espresso 3.00, Latte 4.50, Cappuccino 4.50, "
    "Americano 3.50, Mocha 5.00, Flat White 4.50, Croissant 3.00, "
    "Muffin 2.50, Cheesecake 4.00, Brownie 3.00. Contact us: form below."
)


def _deploy(direct_deploy):
    return direct_deploy(CONTRACT_PATH)


def _create(contract, direct_vm, client, worker, terms=TERMS, amount=1000):
    direct_vm.sender = client
    return contract.create_agreement(worker, terms, amount)


def _agreement(contract, agreement_id):
    return json.loads(contract.get_agreement(agreement_id))


def _dispute(contract, dispute_id):
    return json.loads(contract.get_dispute(dispute_id))


def _mock_adjudication(direct_vm, outcome, share, confidence):
    direct_vm.mock_web(
        r".*evidence\.example\.com.*",
        {"status": 200, "body": EVIDENCE_BODY},
    )
    direct_vm.mock_llm(
        r".*Adjudicate the following dispute.*",
        json.dumps({
            "outcome": outcome,
            "worker_share_bps": share,
            "confidence": confidence,
            "reasoning": "Mocked reasoning based on the terms and evidence.",
        }),
    )


def _ready_dispute(contract, direct_vm, alice, bob):
    """Agreement 1 with a dispute that has both sides submitted."""
    agreement_id = _create(contract, direct_vm, alice, bob)
    direct_vm.sender = alice
    dispute_id = contract.open_dispute(agreement_id, CLAIM, EVIDENCE_URL)
    direct_vm.sender = bob
    contract.submit_response(dispute_id, RESPONSE, EVIDENCE_URL)
    return agreement_id, dispute_id


# --- deterministic agreement lifecycle --------------------------------------

def test_create_agreement_stores_terms_and_parties(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    assert agreement_id == 1
    data = _agreement(contract, agreement_id)
    assert data["status"] == "OPEN"
    assert data["terms"] == TERMS
    assert data["amount"] == 1000
    assert data["clarity_checked"] is False
    assert contract.get_agreement_count() == 1


def test_create_agreement_rejects_same_client_and_worker(direct_vm, direct_deploy, direct_alice):
    contract = _deploy(direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("different accounts"):
        contract.create_agreement(direct_alice, TERMS, 1000)


def test_create_agreement_rejects_empty_terms(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Terms must not be empty"):
        contract.create_agreement(direct_bob, "   ", 1000)


def test_create_agreement_rejects_zero_amount(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Amount must be positive"):
        contract.create_agreement(direct_bob, TERMS, 0)


def test_cancel_agreement_only_by_client_while_open(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the client can cancel"):
        contract.cancel_agreement(agreement_id)

    direct_vm.sender = direct_alice
    contract.cancel_agreement(agreement_id)
    assert _agreement(contract, agreement_id)["status"] == "CANCELLED"


def test_unknown_ids_revert(direct_vm, direct_deploy, direct_alice):
    contract = _deploy(direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Agreement does not exist"):
        contract.get_agreement(99)
    with direct_vm.expect_revert("Dispute does not exist"):
        contract.get_dispute(99)


# --- terms clarity assessment (nondet op #1) ---------------------------------

def test_assess_terms_clear(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.mock_llm(
        r".*Assess whether the following service terms.*",
        json.dumps({"clarity_score": 88, "missing_elements": []}),
    )
    direct_vm.sender = direct_alice
    contract.assess_terms(agreement_id)

    data = _agreement(contract, agreement_id)
    assert data["clarity_checked"] is True
    assert data["terms_clear"] is True
    assert data["clarity_score"] == 88
    assert data["clarity_notes"] == ""


def test_assess_terms_vague(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob, terms=VAGUE_TERMS)

    direct_vm.mock_llm(
        r".*Assess whether the following service terms.*",
        json.dumps({
            "clarity_score": 25,
            "missing_elements": ["no concrete deliverable", "no acceptance criteria", "no deadline"],
        }),
    )
    direct_vm.sender = direct_bob  # either party may run the assessment
    contract.assess_terms(agreement_id)

    data = _agreement(contract, agreement_id)
    assert data["clarity_checked"] is True
    assert data["terms_clear"] is False
    assert data["clarity_score"] == 25
    assert "no deadline" in data["clarity_notes"]


def test_assess_terms_only_parties_and_only_once(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.mock_llm(
        r".*Assess whether the following service terms.*",
        json.dumps({"clarity_score": 90, "missing_elements": []}),
    )
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only a party to the agreement"):
        contract.assess_terms(agreement_id)

    direct_vm.sender = direct_alice
    contract.assess_terms(agreement_id)
    with direct_vm.expect_revert("already assessed"):
        contract.assess_terms(agreement_id)


# --- dispute flow (deterministic guards) -------------------------------------

def test_open_dispute_and_response_flow(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.sender = direct_alice
    dispute_id = contract.open_dispute(agreement_id, CLAIM, EVIDENCE_URL)
    assert dispute_id == 1
    assert _agreement(contract, agreement_id)["status"] == "DISPUTED"

    dispute = _dispute(contract, dispute_id)
    assert dispute["status"] == "AWAITING_RESPONSE"
    assert dispute["claim"] == CLAIM

    # The claimant cannot answer their own claim.
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Only the respondent"):
        contract.submit_response(dispute_id, RESPONSE, EVIDENCE_URL)

    direct_vm.sender = direct_bob
    contract.submit_response(dispute_id, RESPONSE, EVIDENCE_URL)
    assert _dispute(contract, dispute_id)["status"] == "READY"
    assert contract.get_dispute_count() == 1


def test_open_dispute_rejects_non_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only a party to the agreement"):
        contract.open_dispute(agreement_id, CLAIM, EVIDENCE_URL)


def test_resolve_requires_response_first(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id = _create(contract, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    dispute_id = contract.open_dispute(agreement_id, CLAIM, EVIDENCE_URL)

    with direct_vm.expect_revert("has not submitted a response"):
        contract.resolve_dispute(dispute_id)


# --- adjudication (nondet op #2) ----------------------------------------------

def test_resolve_worker_wins(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "WORKER_WINS", 10000, 90)
    direct_vm.sender = direct_alice
    contract.resolve_dispute(dispute_id)

    dispute = _dispute(contract, dispute_id)
    assert dispute["status"] == "RESOLVED"
    assert dispute["outcome"] == "WORKER_WINS"
    assert dispute["worker_share_bps"] == 10000
    assert dispute["confidence"] == 90
    assert _agreement(contract, agreement_id)["status"] == "RESOLVED"


def test_resolve_client_wins(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "CLIENT_WINS", 0, 85)
    direct_vm.sender = direct_bob
    contract.resolve_dispute(dispute_id)

    dispute = _dispute(contract, dispute_id)
    assert dispute["outcome"] == "CLIENT_WINS"
    assert dispute["worker_share_bps"] == 0
    assert _agreement(contract, agreement_id)["status"] == "RESOLVED"


def test_resolve_split(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    _, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "SPLIT", 6000, 70)
    direct_vm.sender = direct_alice
    contract.resolve_dispute(dispute_id)

    dispute = _dispute(contract, dispute_id)
    assert dispute["status"] == "RESOLVED"
    assert dispute["outcome"] == "SPLIT"
    assert dispute["worker_share_bps"] == 6000


def test_resolve_inconclusive_reopens_agreement(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    agreement_id, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "INCONCLUSIVE", 0, 40)
    direct_vm.sender = direct_alice
    contract.resolve_dispute(dispute_id)

    assert _dispute(contract, dispute_id)["status"] == "INCONCLUSIVE"
    assert _agreement(contract, agreement_id)["status"] == "OPEN"

    # The parties can bring a new dispute with better evidence.
    direct_vm.sender = direct_bob
    second_id = contract.open_dispute(agreement_id, "Second attempt with full evidence.", EVIDENCE_URL)
    assert second_id == 2
    assert _agreement(contract, agreement_id)["status"] == "DISPUTED"


def test_double_resolve_rejected(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = _deploy(direct_deploy)
    _, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "WORKER_WINS", 10000, 90)
    direct_vm.sender = direct_alice
    contract.resolve_dispute(dispute_id)

    with direct_vm.expect_revert("already been resolved"):
        contract.resolve_dispute(dispute_id)


def test_resolve_rejects_outsider(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = _deploy(direct_deploy)
    _, dispute_id = _ready_dispute(contract, direct_vm, direct_alice, direct_bob)

    _mock_adjudication(direct_vm, "WORKER_WINS", 10000, 90)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only a party to the dispute"):
        contract.resolve_dispute(dispute_id)
