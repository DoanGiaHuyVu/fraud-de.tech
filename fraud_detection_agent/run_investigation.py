import pandas as pd
import json
import os
import datetime
import time
from tools import generate_all_signals
from agent import get_fraud_decisions_batch

def run_experiment():
    print("Loading transactions.csv...")
    file_path = "../transactions.csv"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
        
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Process ALL rows
    sample_txs = df.to_dict('records')
    
    print(f"Starting batch investigation of {len(sample_txs)} transactions using Gemma 4 Agent...")
    
    all_data = []
    print("Pre-computing signals (this takes a few seconds)...")
    for tx in sample_txs:
        history_df = df[(df['card_id'] == tx['card_id']) & (df['timestamp'] < tx['timestamp'])].copy()
        signals = generate_all_signals(tx, history_df, df)
        
        history_summary = ""
        if len(history_df) > 0:
            last_few = history_df.sort_values('timestamp').tail(3)
            for _, h in last_few.iterrows():
                history_summary += f"- {h['timestamp']} | ${h['amount']} | {h['merchant_name']} | Device: {h['device_id']}\n"
                
        all_data.append({
            "tx": tx,
            "signals": signals,
            "history_summary": history_summary
        })
        
    BATCH_SIZE = 1
    batches = [all_data[i:i + BATCH_SIZE] for i in range(0, len(all_data), BATCH_SIZE)]
    print(f"Created {len(batches)} batches of {BATCH_SIZE} transactions each.")
    
    results = []
    
    print("Executing API calls sequentially to prevent 500 Overload errors...")
    for idx, batch in enumerate(batches):
        max_retries = 3
        decisions = []
        for attempt in range(max_retries):
            decisions = get_fraud_decisions_batch(batch)
            if decisions: # if not empty
                break
            print(f"  Attempt {attempt+1} failed, retrying in 5 seconds...")
            time.sleep(5)
            
        print(f"[{idx+1}/{len(batches)}] Batch finished. Received {len(decisions) if decisions else 0} decisions.")
        
        decision_map = {d.get('transaction_id'): d for d in decisions} if decisions else {}
        
        for item in batch:
            tx_id = item['tx']['transaction_id']
            dec = decision_map.get(tx_id, {"is_fraud": False, "confidence_score": 0.0, "reasoning": "Missing/Error from LLM output"})
            
            res_obj = {
                "transaction_id": tx_id,
                "card_id": item['tx']['card_id'],
                "amount": item['tx']['amount'],
                "signals": item['signals'],
                "agent_decision": dec
            }
            results.append(res_obj)
            
        # Incremental save just in case
        if (idx + 1) % 1 == 0:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            temp_path = os.path.join(log_dir, "agent_investigation_results_partial.json")
            with open(temp_path, "w") as f:
                json.dump(results, f, indent=4)
                
        # Sleep to strictly respect the 15 RPM limit (1 req every 4 seconds)
        time.sleep(4.5)
                
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"agent_investigation_results_{timestamp}_FINAL.json")
    
    with open(log_path, "w") as f:
        json.dump(results, f, indent=4)
        
    print(f"Investigation complete! Final results saved to {log_path}")

if __name__ == "__main__":
    run_experiment()
