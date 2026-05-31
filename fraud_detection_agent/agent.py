from google import genai
import json, os
from dotenv import load_dotenv

load_dotenv('../.env')
MODEL_NAME = "gemma-4-31b-it"

def get_fraud_decisions_batch(batch_data: list) -> list:
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    except Exception as e:
        print(f"Warning: Could not initialize GenAI client: {e}")
        return []
        
    transactions_text = ""
    for idx, item in enumerate(batch_data):
        tx = item['tx']
        signals = item['signals']
        summary = item['history_summary']
        
        transactions_text += f"""
--- TRANSACTION #{idx+1} ---
- Transaction ID: {tx.get('transaction_id')}
- Amount: ${tx.get('amount')}
- Merchant: {tx.get('merchant_name')} (Category: {tx.get('merchant_category')})
- Channel: {tx.get('channel')}
- Cardholder Country: {tx.get('cardholder_country')}
- Merchant Country: {tx.get('merchant_country')}

SIGNAL DETECTORS:
- Cross Border Mismatch: {signals.get('cross_border_mismatch')}
- Amount Multiplier: {signals.get('amount_multiplier'):.1f}x
- Micro-Testing Detected: {signals.get('micro_testing_detected')}
- Missing Device ID: {signals.get('missing_device_id')}
- Fraud Ring Detected: {signals.get('fraud_ring_detected')}

RECENT CARD HISTORY:
{summary or "No previous history for this card."}
"""

    prompt = f"""You are an autonomous AI Fraud Investigator. Your job is to analyze a batch of {len(batch_data)} transactions and determine if each is fraudulent.

{transactions_text}

INVESTIGATION RULES:
1. If 'Fraud Ring Detected' is True, it's highly likely to be fraud.
2. If 'Micro-Testing Detected' is followed by a large transaction, it's highly likely to be fraud.
3. 'Cross Border Mismatch' alone isn't always fraud (could be travel), but combined with 'Missing Device ID' or other factors, it is very suspicious.
4. If the Amount Multiplier is extremely high (e.g., > 10x), this alone is strong evidence of fraud.
5. If >= 2 boolean signals are True, flag as True (Fraud), unless the transaction channel makes it normal.

Output ONLY in this exact JSON format. Your output MUST be a valid JSON array containing exactly {len(batch_data)} objects:
[
  {{
    "transaction_id": "tx_...",
    "is_fraud": true,
    "confidence_score": 0.9,
    "reasoning": "A concise 2-3 sentence explanation."
  }},
  ...
]
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"temperature": 0.1} # Very low temp for strict JSON
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        text = text.replace("```", "").strip()
        decisions = json.loads(text)
        return decisions
    except Exception as e:
        print(f"Failed to generate or parse response: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print("Raw text snippet:", response.text[:500])
        return []
