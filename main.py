import os
import json
from dotenv import load_dotenv

load_dotenv()
import httpx
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Fraud Hunter Reviewer API")

# Allow CORS for local testing if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# GLOBAL MEMORY FOR LIVE-SESSION FEEDBACK LOOP
dismissed_merchants = set()

# GLOBAL CACHE FOR IP GEOLOCATION (Prevents rate-limiting on ip-api.com)
ip_geo_cache = {}

# Load dataframe once into memory for speed
try:
    global_df = pd.read_csv("app_data.csv")
except FileNotFoundError:
    global_df = pd.DataFrame()

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/global_stats")
def get_global_stats():
    """
    Returns global dataset statistics for the Analytics KPI Ribbon.
    """
    total_txs = len(global_df)
    fraud_df = global_df[global_df['probability'] >= 0.80]
    
    fraud_tx_count = len(fraud_df)
    fraud_amount = fraud_df['amount'].sum()
    fraud_percent = (fraud_tx_count / total_txs * 100) if total_txs > 0 else 0
    unique_fraud_clients = fraud_df['card_id'].nunique()
    
    return {
        "defrauded_amount": float(fraud_amount),
        "fraudulent_transactions": int(fraud_tx_count),
        "fraud_percentage": float(fraud_percent),
        "fraudulent_clients": int(unique_fraud_clients)
    }

@app.get("/api/transactions")
def get_transactions(min_probability: float = 0.60, search: str = None):
    """
    Returns transactions where probability >= min_probability, sorted by probability descending.
    Includes Dynamic In-Session Suppression logic and optional search filtering.
    """
    if global_df.empty:
        return {"error": "app_data.csv not found. Did you run data_prep.py?"}
        
    suspicious = global_df.copy()
    
    if search:
        search = search.lower()
        mask = (
            suspicious['card_id'].str.lower().str.contains(search) | 
            suspicious['merchant_name'].str.lower().str.contains(search)
        )
        suspicious = suspicious[mask]
    
    
    # 1. APPLY DYNAMIC SUPPRESSION (FEEDBACK LOOP)
    def apply_suppression(row):
        prob = row['probability']
        if row['merchant_name'] in dismissed_merchants:
            # Penalize probability by 20%
            prob = max(0.0, prob - 0.20)
        return prob

    suspicious['probability'] = suspicious.apply(apply_suppression, axis=1)

    def append_explanation_note(row):
        exp = row['explanation']
        if row['merchant_name'] in dismissed_merchants:
            exp += " • SYSTEM NOTE: You recently dismissed a transaction from this merchant. Risk score dynamically lowered."
        return exp

    suspicious['explanation'] = suspicious.apply(append_explanation_note, axis=1)
    
    # 2. Filter by threshold and sort by risk (Cost-Aware Tuning)
    suspicious = suspicious[suspicious['probability'] >= min_probability].sort_values('probability', ascending=False)
    
    # We round the probability for a cleaner UI display
    suspicious['probability_display'] = suspicious['probability'].apply(lambda x: f"{round(x * 100)}%")
    
    # Use pandas to_json to safely handle NaNs
    return json.loads(suspicious.to_json(orient="records"))

@app.get("/api/card_history/{card_id}")
def get_card_history(card_id: str):
    """Returns the historical timeline of transactions for a specific card."""
    if global_df.empty:
        return []
    history = global_df[global_df['card_id'] == card_id].sort_values('timestamp')
    return json.loads(history.to_json(orient="records"))

@app.get("/api/fraud_ring/{tx_id}")
def get_fraud_ring(tx_id: str):
    """Returns a graph dictionary {nodes: [], edges: []} representing the Entity Relationship Map."""
    if global_df.empty:
        return {"nodes": [], "edges": []}
    
    target = global_df[global_df['transaction_id'] == tx_id]
    if target.empty:
        return {"nodes": [], "edges": []}
        
    start_card = target.iloc[0]['card_id']
    
    # 1. Find all transactions for this card
    card_txs = global_df[global_df['card_id'] == start_card]
    
    ips = set(card_txs['ip_address'].dropna().unique())
    devs = set(card_txs['device_id'].dropna().unique())
    
    # 2. Find all transactions across the dataset that use these IPs or Devices
    ring_mask = global_df['ip_address'].isin(ips) | global_df['device_id'].isin(devs)
    ring_txs = global_df[ring_mask]
    
    nodes = []
    edges = []
    added_nodes = set()
    unique_edges = set()
    
    def add_node(n_id, n_type, label):
        if n_id not in added_nodes:
            # Blue for Cards, Green for Devices, Red for IPs
            color = "#87CEEB" if n_type == "card" else ("#90EE90" if n_type == "device" else "#FA8072")
            nodes.append({"id": n_id, "label": label, "color": color, "shape": "dot", "group": n_type})
            added_nodes.add(n_id)
            
    for _, row in ring_txs.iterrows():
        c_id = row['card_id']
        i_id = row['ip_address']
        d_id = row['device_id']
        
        add_node(c_id, "card", c_id)
        
        if pd.notna(i_id):
            add_node(i_id, "ip", str(i_id))
            e = (c_id, i_id)
            if e not in unique_edges:
                edges.append({"from": c_id, "to": i_id})
                unique_edges.add(e)
                
        if pd.notna(d_id):
            add_node(d_id, "device", str(d_id))
            e = (c_id, d_id)
            if e not in unique_edges:
                edges.append({"from": c_id, "to": d_id})
                unique_edges.add(e)
                
    return {"nodes": nodes, "edges": edges}

@app.get("/api/fraud_ring_map/{tx_id}")
async def get_fraud_ring_map(tx_id: str):
    """
    Returns geographical coordinates for all unique IP addresses in the Fraud Ring
    using a free IP API, with robust local caching.
    """
    if global_df.empty:
        return {"nodes": [], "edges": []}
        
    target = global_df[global_df['transaction_id'] == tx_id]
    if target.empty:
        return {"nodes": [], "edges": []}
        
    start_card = target.iloc[0]['card_id']
    primary_ip = target.iloc[0]['ip_address']
    
    card_txs = global_df[global_df['card_id'] == start_card]
    ips = set(card_txs['ip_address'].dropna().unique())
    devs = set(card_txs['device_id'].dropna().unique())
    
    ring_mask = global_df['ip_address'].isin(ips) | global_df['device_id'].isin(devs)
    ring_txs = global_df[ring_mask]
    
    unique_ips = ring_txs['ip_address'].dropna().unique()
    
    geo_nodes = []
    
    async with httpx.AsyncClient() as client:
        for ip in unique_ips:
            if ip not in ip_geo_cache:
                try:
                    # ip-api.com is free and allows 45 req/min
                    response = await client.get(f"http://ip-api.com/json/{ip}", timeout=3.0)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("status") == "success":
                            ip_geo_cache[ip] = {
                                "lat": data["lat"],
                                "lon": data["lon"],
                                "city": data["city"],
                                "country": data["country"],
                                "region": data.get("regionName", "Unknown"),
                                "isp": data.get("isp", "Unknown"),
                                "asn": data.get("as", "Unknown")
                            }
                except Exception as e:
                    print(f"Failed to geolocate IP {ip}: {e}")
                    pass
                    
            if ip in ip_geo_cache:
                geo_nodes.append({
                    "ip": ip,
                    "is_primary": ip == primary_ip,
                    **ip_geo_cache[ip]
                })
                
    # We will draw edges connecting the primary IP to all other IPs in the ring
    edges = []
    if primary_ip and primary_ip in ip_geo_cache:
        for ip in unique_ips:
            if ip != primary_ip and ip in ip_geo_cache:
                edges.append({"from": primary_ip, "to": ip})
                
    return {"nodes": geo_nodes, "edges": edges}

@app.get("/api/merchant_volume/{merchant_name}")
def get_merchant_volume(merchant_name: str):
    """
    Returns the daily transaction volume (count and total amount) for a specific merchant.
    Used to visualize Pattern 2: Coordinated Merchant Attack Waves.
    """
    if global_df.empty:
        return []
        
    merchant_txs = global_df[global_df['merchant_name'] == merchant_name]
    if merchant_txs.empty:
        return []
        
    # Group by date and calculate daily velocity
    merchant_txs = merchant_txs.copy()
    merchant_txs['date_dt'] = pd.to_datetime(merchant_txs['date'])
    
    daily_volume = merchant_txs.groupby(merchant_txs['date_dt'].dt.strftime('%Y-%m-%d')).agg(
        transaction_count=('transaction_id', 'count'),
        total_amount=('amount', 'sum')
    )
    
    # Reindex to ensure a continuous 30-day timeline
    global_dates = pd.to_datetime(global_df['date'])
    min_date = global_dates.min()
    max_date = global_dates.max()
    full_date_range = pd.date_range(start=min_date, end=max_date).strftime('%Y-%m-%d')
    
    daily_volume = daily_volume.reindex(full_date_range, fill_value=0)
    daily_volume.index.name = 'date'
    daily_volume = daily_volume.reset_index()
    
    return daily_volume.to_dict(orient="records")

@app.get("/api/risk_factors/{tx_id}")
def get_risk_factors(tx_id: str):
    """
    Returns a 0-100 score for 5 distinct risk categories for the Radar Chart.
    """
    if global_df.empty:
        return {"Location": 0, "Velocity": 0, "Device": 0, "Amount": 0, "Network": 0}
        
    tx = global_df[global_df['transaction_id'] == tx_id]
    if tx.empty:
        return {"Location": 0, "Velocity": 0, "Device": 0, "Amount": 0, "Network": 0}
        
    row = tx.iloc[0]
    
    # 1. Location Risk (Cross Border + IP matching)
    loc_risk = 0
    if row['is_cross_border'] == 1:
        loc_risk += 60
    if row['cardholder_country'] != row['merchant_country']:
        loc_risk += 30
        
    # 2. Velocity Risk (Micro-tx or High Volume)
    vel_risk = 0
    if row['is_micro_tx'] == 1:
        vel_risk = 90
    else:
        # Simulate velocity risk based on probability
        vel_risk = int(row['probability'] * 60)
        
    # 3. Device Risk
    dev_risk = 0
    if row['device_id_missing'] == 1:
        dev_risk = 85
    else:
        dev_risk = 10
        
    # 4. Amount Anomaly
    amt_scaled = row['amount_scaled']
    if pd.isna(amt_scaled):
        amt_risk = 0
    else:
        # 1.0 is normal. 5.0 is 5x normal. Cap at 100
        amt_risk = min(100, max(0, int((amt_scaled - 1.0) * 20)))
        
    # 5. Network Risk (Fraud Ring)
    net_risk = 95 if row['is_fraud_ring'] == 1 else int(row['probability'] * 40)
    
    return {
        "Location": min(100, loc_risk),
        "Velocity": min(100, vel_risk),
        "Device": min(100, dev_risk),
        "Amount": min(100, amt_risk),
        "Network": min(100, net_risk)
    }

@app.post("/api/analyze_gemma")
async def analyze_gemma(request: Request):
    """
    Securely proxies the Gemma 4 31B LLM to generate a textual reasoning.
    """
    data = await request.json()
    
    # Extract params to build prompt
    prob = data.get("probability", 0) * 100
    tx_id = data.get("transaction_id", "Unknown")
    amount = data.get("amount", 0)
    merchant = data.get("merchant_name", "Unknown")
    is_cross = data.get("is_cross_border", 0)
    is_ring = data.get("is_fraud_ring", 0)
    
    prompt = (
        f"You are a Senior Trust and Safety Analyst. Act extremely professional and direct. "
        f"Analyze transaction {tx_id}. It was processed for ${amount} at '{merchant}'. "
        f"The machine learning model flagged it with a fraud probability of {prob:.0f}%. "
        f"Please explain why this transaction is risky or safe in exactly 2-3 short, punchy sentences. "
    )
    if is_cross:
        prompt += "Mention the fact that this is a cross-border transaction with impossible travel involved. "
    if is_ring:
        prompt += "Mention the fact that the IP/Device signature matches a known Fraud Ring involving multiple stolen cards. "
        
    prompt += "End your response with a <b>Recommendation</b>: specifically tell the human analyst to either 'Approve', 'Dismiss', or 'Escalate' the transaction."

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return {"analysis": "[Error] GEMINI_API_KEY environment variable not set. Set it with: export GEMINI_API_KEY=your_key"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                return {"analysis": f"API Error: {resp.status_code} - {resp.text}"}
            
            resp_data = resp.json()
            # Extract generated text from Gemma's response
            text = resp_data["candidates"][0]["content"]["parts"][-1]["text"]
            # Replace newlines with <br> for HTML rendering
            text = text.replace("\n", "<br>")
            return {"analysis": text}
        except Exception as e:
            return {"analysis": f"Error reaching AI API: {type(e).__name__} - {str(e)}"}

@app.post("/api/decision")
async def log_decision(request: Request):
    """
    Logs the analyst's decision (approve, dismiss, escalate) to the audit trail
    and applies the live feedback loop (merchant suppression on Dismiss).
    """
    data = await request.json()
    # Support both 'tx_id' and 'transaction_id' keys from different callers
    tx_id = data.get("transaction_id") or data.get("tx_id", "Unknown")
    decision = data.get("decision", "Unknown")

    # Audit Trail Fields
    reason = data.get("escalation_reason", "")
    notes = data.get("analyst_notes", "")

    print(f"\n[{decision.upper()}] Transaction {tx_id} processed.")
    if decision.lower() == "escalate":
        print(f"   └─ Reason: {reason}")
        print(f"   └─ Notes: {notes}")

    # LIVE FEEDBACK LOOP: If dismissed, remember the merchant and suppress its score
    merchant_suppressed = False
    if decision.lower() == "dismiss" and tx_id:
        tx_row = global_df[global_df['transaction_id'] == tx_id]
        if not tx_row.empty:
            merchant = tx_row.iloc[0]['merchant_name']
            dismissed_merchants.add(merchant)
            merchant_suppressed = True
            print(f"--- DYNAMIC SUPPRESSION ENGAGED: Suppressing future flags for '{merchant}' ---")

    # Log to audit trail (Receipt / Audit Trail requirement)
    decision_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_id": tx_id,
        "decision": decision,
        "probability_score": data.get("probability"),
        "escalation_reason": reason,
        "analyst_notes": notes,
    }

    log_file = "audit_log.json"
    audit_trail = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                audit_trail = json.load(f)
            except json.JSONDecodeError:
                pass

    audit_trail.append(decision_entry)

    with open(log_file, "w") as f:
        json.dump(audit_trail, f, indent=2)
        
    return {"status": "success", "logged": True, "merchant_suppressed": merchant_suppressed}

@app.post("/api/undo")
async def undo_decision(request: Request):
    """
    Reverts the last analyst decision:
    - If the reverted decision was 'Dismiss', removes the merchant from dismissed_merchants
      so its risk score returns to normal on the next queue fetch.
    - Always appends an UNDO entry to audit_log.json for the compliance trail.
    """
    data = await request.json()
    tx_id = data.get("transaction_id", "Unknown")
    previous_decision = data.get("previous_decision", "Unknown")

    merchant_unsuppressed = False
    if previous_decision.lower() == "dismiss" and tx_id:
        tx_row = global_df[global_df['transaction_id'] == tx_id]
        if not tx_row.empty:
            merchant = tx_row.iloc[0]['merchant_name']
            dismissed_merchants.discard(merchant)
            merchant_unsuppressed = True
            print(f"--- UNDO: Re-activating risk score for '{merchant}' ---")

    undo_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_id": tx_id,
        "decision": "UNDO",
        "reverted_decision": previous_decision,
    }

    log_file = "audit_log.json"
    audit_trail = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                audit_trail = json.load(f)
            except json.JSONDecodeError:
                pass
    audit_trail.append(undo_entry)
    with open(log_file, "w") as f:
        json.dump(audit_trail, f, indent=2)

    return {"status": "success", "merchant_unsuppressed": merchant_unsuppressed}
