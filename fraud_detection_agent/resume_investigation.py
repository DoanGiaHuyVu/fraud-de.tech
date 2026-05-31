import pandas as pd
import json
import os
import datetime
import time
import glob
from tools import generate_all_signals
from agent import get_fraud_decisions_batch

def resume_experiment():
    print("Loading transactions.csv...")
    file_path = "../transactions.csv"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
        
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Process ALL rows
    sample_txs = df.to_dict('records')
    
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print("No logs directory found. Run run_investigation.py first.")
        return
        
    # Find the most recent partial or final log
    log_files = glob.glob(os.path.join(log_dir, "agent_investigation_results_*.json"))
    if not log_files:
        print("No log files found to resume from.")
        return
        
    latest_log = max(log_files, key=os.path.getctime)
    print(f"Resuming from {latest_log}...")
    
    with open(latest_log, 'r') as f:
        existing_results = json.load(f)
        
    # Find which transactions have successful decisions
    successful_tx_ids = set()
    for res in existing_results:
        reasoning = res.get('agent_decision', {}).get('reasoning', '')
        if "Missing/Error" not in reasoning and reasoning != "":
            successful_tx_ids.add(res.get('transaction_id'))
            
    print(f"Found {len(successful_tx_ids)} successfully processed transactions.")
    
    # Filter the sample_txs to only include the missing ones
    missing_txs = [tx for tx in sample_txs if tx['transaction_id'] not in successful_tx_ids]
    
    if not missing_txs:
        print("All transactions have already been processed successfully!")
        return
        
    print(f"Need to process {len(missing_txs)} missing transactions...")
    
    all_data = []
    print("Pre-computing signals (this takes a few seconds)...")
    for tx in missing_txs:
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
    
    results_map = {r['transaction_id']: r for r in existing_results}
    
    print("Executing API calls sequentially with high retry limits...")
    for idx, batch in enumerate(batches):
        max_retries = 10 # Increased to 10 for resilience against Google 503 errors
        decisions = []
        for attempt in range(max_retries):
            decisions = get_fraud_decisions_batch(batch)
            if decisions: # if not empty
                break
            print(f"  Attempt {attempt+1} failed, retrying in 10 seconds...")
            time.sleep(10) # Increased backoff to 10 seconds
            
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
            results_map[tx_id] = res_obj
            
        # Incremental save
        if (idx + 1) % 1 == 0:
            temp_path = os.path.join(log_dir, "agent_investigation_results_partial.json")
            with open(temp_path, "w") as f:
                json.dump(list(results_map.values()), f, indent=4)
                
        time.sleep(4.5)
                
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"agent_investigation_results_{timestamp}_FINAL.json")
    
    with open(log_path, "w") as f:
        json.dump(list(results_map.values()), f, indent=4)
        
    print(f"Investigation complete! Final patched results saved to {log_path}")

if __name__ == "__main__":
    resume_experiment()
