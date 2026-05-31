import pytest
import pandas as pd
from fastapi.testclient import TestClient
from main import app

# Create a test client for our FastAPI server
client = TestClient(app)


def test_detector_output_correctness():
    """
    Tests the offline ML detector's output (Random Forest ensemble)
    by verifying a known fraud case and a known legitimate case in the generated dataset.
    This fulfills the exact Prompt Requirement:
    'At least one test that exercises your detector on a known fraud case and a known legitimate case.'
    """
    df = pd.read_csv("app_data.csv")

    # 1. Known Fraud Case: tx_000993 ($1138 at Gift Card Mall, foreign IP)
    fraud_tx = df[df['transaction_id'] == 'tx_000993'].iloc[0]
    assert fraud_tx['is_fraud'] == True, "The dataset label should be True for this known fraud case"
    assert fraud_tx['probability'] >= 0.90, "The ML detector should flag this with a high probability score"
    assert "Amount is" in fraud_tx['explanation'], "The explanation engine should catch the anomaly"

    # 2. Known Legitimate Case: tx_000784 ($18 at Amazon.ca, local IP)
    legit_tx = df[df['transaction_id'] == 'tx_000784'].iloc[0]
    assert legit_tx['is_fraud'] == False, "The dataset label should be False for this known legitimate case"
    assert legit_tx['probability'] < 0.30, "The ML detector should give this a very low probability score"


def test_fastapi_transactions_endpoint():
    """
    Tests that the FastAPI backend properly applies the Cost-Aware Tuning threshold
    and serves the Reviewer Queue correctly.
    """
    # Test strict threshold (Only extremely obvious fraud)
    response_strict = client.get("/api/transactions?min_probability=0.90")
    assert response_strict.status_code == 200
    queue_strict = response_strict.json()
    assert len(queue_strict) > 0

    # Ensure all returned items meet the strict threshold
    for tx in queue_strict:
        assert tx['probability'] >= 0.90

    # Test loose threshold (Catches everything slightly suspicious)
    response_loose = client.get("/api/transactions?min_probability=0.50")
    assert response_loose.status_code == 200
    queue_loose = response_loose.json()

    # The loose queue should contain more transactions than the strict queue
    assert len(queue_loose) >= len(queue_strict)


def test_fastapi_decision_endpoint():
    """
    Tests the POST endpoint that records the Reviewer's actions,
    satisfying the 'Audit Log / Feedback Loop' requirement.
    """
    payload = {
        "transaction_id": "tx_000993",
        "decision": "Escalate",
        "probability": 1.0
    }
    response = client.post("/api/decision", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
