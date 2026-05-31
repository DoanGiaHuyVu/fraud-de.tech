import pytest
from fastapi.testclient import TestClient
from main import app, dismissed_merchants

client = TestClient(app)

def test_dynamic_suppression_feedback_loop():
    # 1. Reset the global memory just in case
    dismissed_merchants.clear()

    # 2. Get the initial state of the queue
    response_initial = client.get("/api/transactions?min_probability=0.0")
    initial_queue = response_initial.json()
    
    # Pick a random transaction to "Dismiss"
    target_tx = initial_queue[0]
    tx_id = target_tx["transaction_id"]
    target_merchant = target_tx["merchant_name"]
    initial_prob = target_tx["probability"]

    # 3. Simulate the human hitting "Dismiss" in the UI
    payload = {
        "transaction_id": tx_id,
        "decision": "Dismiss",
        "probability": initial_prob
    }
    post_response = client.post("/api/decision", json=payload)
    assert post_response.status_code == 200
    assert post_response.json()["merchant_suppressed"] == True

    # 4. Fetch the queue AGAIN and verify the dynamic suppression engaged!
    response_updated = client.get("/api/transactions?min_probability=0.0")
    updated_queue = response_updated.json()
    
    # Find that same transaction in the updated queue
    updated_tx = next(tx for tx in updated_queue if tx["transaction_id"] == tx_id)
    
    # Assert the probability was lowered by exactly 20% (0.20)
    assert round(updated_tx["probability"], 2) == round(max(0.0, initial_prob - 0.20), 2)
    
    # Assert the UI explanation string successfully appended the System Note
    assert "SYSTEM NOTE: You recently dismissed a transaction from this merchant" in updated_tx["explanation"]
    
    print("\nSUCCESS! The feedback loop correctly suppressed the merchant and updated the UI explanation.")


def test_approve_decision_no_suppression():
    """
    When a human clicks 'Approve' (confirming the fraud), the merchant should NOT be suppressed,
    and the score should remain the same.
    """
    dismissed_merchants.clear()

    response_initial = client.get("/api/transactions?min_probability=0.0")
    initial_queue = response_initial.json()
    
    # Pick a random transaction to "Approve"
    target_tx = initial_queue[1]  # Pick the second one
    tx_id = target_tx["transaction_id"]
    initial_prob = target_tx["probability"]

    # Simulate the human hitting "Approve" in the UI
    payload = {
        "transaction_id": tx_id,
        "decision": "Approve",
        "probability": initial_prob
    }
    post_response = client.post("/api/decision", json=payload)
    assert post_response.status_code == 200
    assert post_response.json()["merchant_suppressed"] == False

    # Fetch the queue AGAIN and verify the score did NOT drop
    response_updated = client.get("/api/transactions?min_probability=0.0")
    updated_queue = response_updated.json()
    
    updated_tx = next(tx for tx in updated_queue if tx["transaction_id"] == tx_id)
    
    assert round(updated_tx["probability"], 2) == round(initial_prob, 2)
    assert "SYSTEM NOTE" not in updated_tx["explanation"]
    
    print("\nSUCCESS! Hitting 'Approve' did not trigger the suppression logic.")
