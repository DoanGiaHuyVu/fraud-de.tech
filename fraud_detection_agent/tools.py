import pandas as pd
import numpy as np

def check_cross_border(tx):
    # If both are known and not equal, it's a cross-border transaction
    card_country = tx.get('cardholder_country')
    merchant_country = tx.get('merchant_country')
    if pd.isna(card_country) or pd.isna(merchant_country):
        return False
    return card_country != merchant_country

def check_amount_anomaly(tx, history_df):
    amt = tx.get('amount', 0.0)
    if pd.isna(amt):
        return 0.0
    if len(history_df) == 0:
        return 0.0 # No baseline
    median_amt = history_df['amount'].median()
    if pd.isna(median_amt) or median_amt == 0:
        return 0.0
    return float(amt / median_amt)

def check_micro_testing(tx, history_df, time_window_minutes=60):
    # Check if there is a micro tx (< $2) in the history within time_window_minutes
    if len(history_df) == 0:
        return False
    
    current_time = pd.to_datetime(tx['timestamp'])
    
    # Filter history by time window
    history_df = history_df.copy()
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    
    recent_txs = history_df[
        (history_df['timestamp'] < current_time) & 
        (history_df['timestamp'] >= (current_time - pd.Timedelta(minutes=time_window_minutes)))
    ]
    
    has_micro = (recent_txs['amount'] < 2.0).any()
    return bool(has_micro)

def check_missing_device(tx):
    if tx.get('channel') == 'in_person':
        return False
    device = tx.get('device_id')
    return pd.isna(device) or str(device).strip() == ""

def check_fraud_ring(tx, all_tx_df):
    device = tx.get('device_id')
    ip = tx.get('ip_address')
    
    is_ring = False
    if pd.notna(device) and str(device).strip() != "":
        # How many distinct cards used this device?
        cards_with_device = all_tx_df[all_tx_df['device_id'] == device]['card_id'].nunique()
        if cards_with_device > 1:
            is_ring = True
            
    if pd.notna(ip) and str(ip).strip() != "":
        # How many distinct cards used this IP?
        cards_with_ip = all_tx_df[all_tx_df['ip_address'] == ip]['card_id'].nunique()
        if cards_with_ip > 1:
            is_ring = True
            
    return is_ring

def generate_all_signals(tx, history_df, all_tx_df):
    return {
        "cross_border_mismatch": bool(check_cross_border(tx)),
        "amount_multiplier": float(check_amount_anomaly(tx, history_df)),
        "micro_testing_detected": bool(check_micro_testing(tx, history_df)),
        "missing_device_id": bool(check_missing_device(tx)),
        "fraud_ring_detected": bool(check_fraud_ring(tx, all_tx_df))
    }
