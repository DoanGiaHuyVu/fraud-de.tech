let queue = [];
let currentIndex = 0;
let historyStack = [];

const slider = document.getElementById('threshold');
const thresholdVal = document.getElementById('threshold-val');
const queueCount = document.getElementById('queue-count');
const txCard = document.getElementById('transaction-card');
const emptyState = document.getElementById('empty-state');
const loading = document.getElementById('loading');

let cardHistoryChartInst = null;
let fraudRingChartInst = null;
let merchantVolumeChartInst = null;
let riskRadarChartInst = null;
let gemmaTypingInterval = null;

// DOM Elements for Tx Data
const merchant = document.getElementById('merchant');
const riskScore = document.getElementById('risk-score');
const amount = document.getElementById('amount');
const cardId = document.getElementById('card-id');
const date = document.getElementById('date');
const locationText = document.getElementById('location-text');
const decisionSummary = document.getElementById('decision-summary');
const tagsContainer = document.getElementById('tags-container');
const explanation = document.getElementById('explanation');

// DOM Elements for Visualizer
const barMedian = document.getElementById('bar-median');
const barCurrent = document.getElementById('bar-current');
const valMedian = document.getElementById('val-median');
const valCurrent = document.getElementById('val-current');
const valRatio = document.getElementById('val-ratio');
const riskList = document.getElementById('risk-list');

async function fetchQueue() {
    const minProb = slider.value / 100;
    
    txCard.classList.add('hidden');
    emptyState.classList.add('hidden');
    loading.classList.remove('hidden');

    const searchInput = document.getElementById('search-filter').value.trim();
    let url = `/api/transactions?min_probability=${minProb}`;
    if (searchInput) {
        url += `&search=${encodeURIComponent(searchInput)}`;
    }

    try {
        const res = await fetch(url);
        const data = await res.json();
        
        queue = data;
        currentIndex = 0;
        
        loading.classList.add('hidden');
        renderCurrentTx();
    } catch (e) {
        console.error("Failed to fetch queue", e);
        loading.innerText = "Error loading queue. Is the FastAPI server running?";
    }
}

function renderCurrentTx() {
    queueCount.innerText = queue.length - currentIndex;

    if (currentIndex >= queue.length) {
        txCard.classList.add('hidden');
        emptyState.classList.remove('hidden');
        return;
    }

    const tx = queue[currentIndex];
    
    merchant.innerText = tx.merchant_name || 'Unknown Merchant';
    riskScore.innerText = `${Math.round(tx.probability * 100)}%`;
    
    amount.innerText = `$${parseFloat(tx.amount).toFixed(2)}`;
    cardId.innerText = tx.card_id;
    date.innerText = tx.date;
    locationText.innerText = `${tx.cardholder_country} → ${tx.merchant_country}`;
    
    // Clean up explanation (handle both comma and bullet separators)
    let rawExp = tx.explanation.replace(/•/g, ','); 
    let exps = rawExp.split(',').map(s => s.trim()).filter(s => s.length > 0);
    
    if (exps.length === 1) {
        explanation.innerHTML = exps[0];
    } else {
        explanation.innerHTML = exps.map(s => `• ${s}`).join('<br>');
    }
    explanation.style.fontStyle = 'normal';
    
    // Bind Gemma Button
    const btnGemma = document.getElementById('btn-gemma');
    if (btnGemma) {
        const newBtn = btnGemma.cloneNode(true);
        btnGemma.parentNode.replaceChild(newBtn, btnGemma);
        
        newBtn.addEventListener('click', async () => {
            newBtn.innerText = "Processing...";
            newBtn.disabled = true;
            
            try {
                const res = await fetch('/api/analyze_gemma', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(tx)
                });
                const data = await res.json();
                
                const aiText = `[Sentinel AI Analysis]\n\n` + data.analysis;
                streamGemmaText(aiText, newBtn);
            } catch (e) {
                streamGemmaText("[Error] Failed to connect to API.", newBtn);
            }
        });
    }

    // Render Tags & Risk List
    tagsContainer.innerHTML = '';
    riskList.innerHTML = '';
    
    let risks = [];
    if (tx.is_cross_border === 1) {
        tagsContainer.innerHTML += `<span class="tag danger">Cross-Border</span>`;
        risks.push({ label: 'Cross-border mismatch detected', severity: 'danger' });
    }
    
    if (tx.is_fraud_ring === 1) {
        tagsContainer.innerHTML += `<span class="tag danger">Fraud Ring</span>`;
        risks.push({ label: 'Connected to known fraud ring entities', severity: 'danger' });
    }
    
    if (tx.amount_scaled && tx.amount_scaled > 0) {
        let mult = (tx.amount / tx.amount_scaled).toFixed(1);
        if (mult > 10) {
            risks.push({ label: `Transaction is ${mult}× above card baseline`, severity: 'danger' });
        } else if (mult > 2) {
            risks.push({ label: `Transaction is ${mult}× above card baseline`, severity: 'warning' });
        }
    }
    
    if (tx.merchant_category) {
        risks.push({ label: `${tx.merchant_category} merchant category detected`, severity: 'warning' });
    } else if (tx.merchant_name && tx.merchant_name.toLowerCase().includes('gift')) {
        risks.push({ label: `Gift card merchant category detected`, severity: 'warning' });
    }
    
    if (tx.is_micro_tx === 1) {
        tagsContainer.innerHTML += `<span class="tag">Micro-Tx</span>`;
        risks.push({ label: 'Suspicious micro-transaction (card testing)', severity: 'warning' });
    }
    
    if (tx.device_id_missing === 1) {
        tagsContainer.innerHTML += `<span class="tag">No Device ID</span>`;
        risks.push({ label: 'Device ID missing or cloaked', severity: 'warning' });
    }
    
    if (risks.length === 0) {
        riskList.innerHTML = `<li style="color: var(--text-muted); list-style: none;">No extreme risk factors matched</li>`;
    } else {
        risks.forEach(r => {
            const dotColor = r.severity === 'danger' ? 'var(--danger)' : 'var(--warning)';
            riskList.innerHTML += `<div class="risk-item"><div class="risk-dot" style="background:${dotColor}"></div> <span>${r.label}</span></div>`;
        });
    }

    // Render Baseline
    const currentAmt = parseFloat(tx.amount);
    let medianAmt = 0;
    if (tx.amount_scaled && tx.amount_scaled > 0) {
        medianAmt = currentAmt / tx.amount_scaled;
    }

    valMedian.innerText = `$${medianAmt.toFixed(2)}`;
    valCurrent.innerText = `$${currentAmt.toFixed(2)}`;

    let multiplier = "Unknown";
    if (medianAmt > 0) {
        multiplier = (currentAmt / medianAmt).toFixed(1);
        valRatio.innerText = `${multiplier}x Baseline`;
    } else {
        valRatio.innerText = `First Tx`;
    }

    // Decision Summary
    decisionSummary.innerText = `Transaction from a ${tx.cardholder_country} card at a ${tx.merchant_country} merchant, ${multiplier !== "Unknown" ? multiplier + '× above' : 'against'} typical baseline.`;

    if (currentAmt > medianAmt * 2) {
        barMedian.style.width = '10%';
        barCurrent.style.width = '100%';
    } else if (currentAmt > medianAmt) {
        barMedian.style.width = '50%';
        barCurrent.style.width = '100%';
    } else {
        barMedian.style.width = '100%';
        barCurrent.style.width = `${Math.max(10, (currentAmt / medianAmt) * 100)}%`;
    }

    renderCharts(tx);

    txCard.classList.remove('hidden');
    emptyState.classList.add('hidden');
}

function handleAction(decision) {
    if (currentIndex >= queue.length) return;
    
    const tx = queue[currentIndex];
    
    historyStack.push({
        index: currentIndex,
        tx: tx,
        decision: decision
    });

    if (decision === 'Escalate') {
        const modal = document.getElementById('escalation-modal');
        modal.classList.add('show');
        document.getElementById('escalation-notes').value = '';
        document.getElementById('escalation-notes').focus();
        
        const modalMerchant = document.getElementById('modal-merchant');
        const modalCardId = document.getElementById('modal-card-id');
        const modalAmount = document.getElementById('modal-amount');
        const modalRisk = document.getElementById('modal-risk');
        
        if (modalMerchant) modalMerchant.innerText = tx.merchant_name || 'Unknown';
        if (modalCardId) modalCardId.innerText = tx.card_id || 'Unknown';
        if (modalAmount) modalAmount.innerText = `$${parseFloat(tx.amount).toFixed(2)}`;
        if (modalRisk) modalRisk.innerText = `${Math.round(tx.probability * 100)}%`;
        
        const btnCancel = document.getElementById('btn-modal-cancel');
        const btnSubmit = document.getElementById('btn-modal-submit');
        const newCancel = btnCancel.cloneNode(true);
        const newSubmit = btnSubmit.cloneNode(true);
        btnCancel.parentNode.replaceChild(newCancel, btnCancel);
        btnSubmit.parentNode.replaceChild(newSubmit, btnSubmit);
        
        newCancel.addEventListener('click', () => {
            modal.classList.remove('show');
        });
        
        newSubmit.addEventListener('click', () => {
            const reason = document.getElementById('escalation-reason').value;
            const notes = document.getElementById('escalation-notes').value;
            modal.classList.remove('show');
            submitDecision(tx.transaction_id, decision, tx.probability, reason, notes);
        });
        return;
    }

    submitDecision(tx.transaction_id, decision, tx.probability, "", "");
}

function submitDecision(txId, decision, probability, reason, notes) {
    // Show Toast
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-msg');
    toastMsg.innerText = `${decision} action recorded.`;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4000);

    fetch('/api/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            tx_id: txId,
            decision: decision,
            probability: probability,
            escalation_reason: reason,
            analyst_notes: notes
        })
    }).then(res => res.json()).then(data => {
        if (data.merchant_suppressed) {
            fetchQueue();
        } else {
            currentIndex++;
            renderCurrentTx();
        }
    }).catch(e => {
        currentIndex++;
        renderCurrentTx();
    });
}

async function undoAction() {
    if (historyStack.length === 0) return;
    const lastAction = historyStack.pop();

    // Tell the server to revert the decision (removes merchant suppression if it was a Dismiss
    // and writes an UNDO entry to audit_log.json for the compliance trail)
    try {
        const res = await fetch('/api/undo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                transaction_id: lastAction.tx.transaction_id,
                previous_decision: lastAction.decision
            })
        });
        const data = await res.json();
        // If a Dismiss was undone the merchant suppression is gone — refetch so scores reset
        if (data.merchant_unsuppressed) {
            currentIndex = lastAction.index;
            await fetchQueue();
            return;
        }
    } catch (e) {
        console.warn('Undo API call failed, reverting UI only:', e);
    }

    // Restore the UI position and dismiss any lingering toast
    currentIndex = lastAction.index;
    const toast = document.getElementById('toast');
    toast.classList.remove('show');
    renderCurrentTx();
}

slider.addEventListener('input', (e) => {
    thresholdVal.innerText = `${e.target.value}%`;
});
slider.addEventListener('change', fetchQueue);

// Button Action Listeners (Removed click events as per keyboard-only design)
// document.getElementById('btn-act-approve').addEventListener('click', () => handleAction('Approve'));
// document.getElementById('btn-act-dismiss').addEventListener('click', () => handleAction('Dismiss'));
// document.getElementById('btn-act-escalate').addEventListener('click', () => handleAction('Escalate'));

const btnUndo = document.getElementById('btn-undo');
if (btnUndo) btnUndo.addEventListener('click', undoAction);


document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('escalation-modal');
    const isModalOpen = modal && modal.classList.contains('show');

    // Handle Escape key to close the modal
    if (e.key === 'Escape' && isModalOpen) {
        modal.classList.remove('show');
        return;
    }

    // Do not process other keyboard shortcuts if the modal is open
    if (isModalOpen) return;

    if (document.activeElement === slider) return;
    if (document.activeElement.tagName === 'TEXTAREA' || document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') return;
    
    if (e.key.toLowerCase() === 'a') handleAction('Approve');
    if (e.key.toLowerCase() === 'd') handleAction('Dismiss');
    if (e.key.toLowerCase() === 'e') handleAction('Escalate');
    if (e.key.toLowerCase() === 'z') undoAction();
});

// Grid Layout: Charts are rendered simultaneously without tabs.

// Search filter listener (Debounced)
let searchTimeout;
document.getElementById('search-filter').addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(fetchQueue, 300);
});

// Initial Load
fetchQueue();

async function renderCharts(tx) {
    // 1. Card History
    try {
        const res = await fetch(`/api/card_history/${tx.card_id}`);
        const historyData = await res.json();
        
        const labels = historyData.map(t => t.date);
        const data = historyData.map(t => t.amount);
        const bgColors = historyData.map(t => t.transaction_id === tx.transaction_id ? '#EF4444' : '#4187FF');
        
        const ctxHist = document.getElementById('cardHistoryChart').getContext('2d');
        if (cardHistoryChartInst) cardHistoryChartInst.destroy();
        
        cardHistoryChartInst = new Chart(ctxHist, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Amount (CAD)',
                    data: data,
                    backgroundColor: bgColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { 
                        beginAtZero: true, 
                        grid: { color: 'rgba(190, 195, 206, 0.10)' }, 
                        ticks: { color: '#BEC3CE', maxTicksLimit: 5, font: { size: 10 } } 
                    },
                    x: { display: false }
                }
            }
        });
    } catch (e) { console.error(e); }
    
    // 1.5 Risk Factor Radar Chart
    try {
        const resRisk = await fetch(`/api/risk_factors/${tx.transaction_id}`);
        const riskData = await resRisk.json();
        
        const rLabels = ['Location', 'Velocity', 'Device', 'Amount Anomaly', 'Network Ring'];
        const rData = [riskData.Location, riskData.Velocity, riskData.Device, riskData.Amount, riskData.Network];
        
        const ctxRadar = document.getElementById('riskRadarChart').getContext('2d');
        if (riskRadarChartInst) riskRadarChartInst.destroy();
        
        riskRadarChartInst = new Chart(ctxRadar, {
            type: 'radar',
            data: {
                labels: rLabels,
                datasets: [{
                    label: 'Risk Score',
                    data: rData,
                    backgroundColor: 'rgba(239, 68, 68, 0.18)',
                    borderColor: '#EF4444',
                    pointBackgroundColor: '#EF4444',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    r: {
                        angleLines: { display: false },
                        grid: { color: 'rgba(168, 200, 255, 0.12)', circular: true },
                        pointLabels: { color: '#BEC3CE', font: { size: 10, weight: '500' } },
                        ticks: { display: false, min: 0, max: 100 }
                    }
                }
            }
        });
    } catch (e) { }

    // 2. Fraud Ring Network
    try {
        const resRing = await fetch(`/api/fraud_ring/${tx.transaction_id}`);
        const ringData = await resRing.json();
        
        const ringStats = document.getElementById('fraud-ring-stats');
        const container = document.getElementById('fraudRingChart');
        
        if (fraudRingChartInst && typeof fraudRingChartInst.destroy === 'function') {
            fraudRingChartInst.destroy();
        }

        if (ringData.nodes.length <= 1) {
            ringStats.innerText = "Isolated Transaction";
            ringStats.style.color = "var(--success)";
            container.innerHTML = "<div style='padding:2rem;text-align:center;color:var(--text-muted);'>No connected entities found.</div>";
            fraudRingChartInst = null;
        } else {
            const numCards = ringData.nodes.filter(n => n.group === 'card').length;
            ringStats.innerText = `${numCards} distinct cards connected`;
            ringStats.style.color = "var(--danger)";
            
            // Create the Vis.js data structure
            const data = { nodes: new vis.DataSet(ringData.nodes), edges: new vis.DataSet(ringData.edges) };
            const options = {
                nodes: { borderWidth: 2, size: 22, font: { color: '#F7FAFF', size: 13, face: 'Roboto' } },
                edges: { color: { color: 'rgba(190, 195, 206, 0.14)', highlight: '#0F68FF' }, width: 2, smooth: true },
                physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.005, springLength: 140, springConstant: 0.04 } },
                interaction: { dragNodes: true, dragView: false, zoomView: false, hover: true }
            };
            fraudRingChartInst = new vis.Network(container, data, options);
            
            // Zoom toggle and cross-component mapping
            let lastFocusedNode = null;
            
            fraudRingChartInst.on("click", function(params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    
                    // If clicking the same node again, zoom out to fit the graph
                    if (nodeId === lastFocusedNode) {
                        fraudRingChartInst.fit({
                            animation: { duration: 600, easingFunction: "easeInOutQuad" }
                        });
                        fraudRingChartInst.unselectAll();
                        lastFocusedNode = null;
                    } else {
                        // First click: zoom in
                        fraudRingChartInst.focus(nodeId, {
                            scale: 2.0,
                            animation: { duration: 600, easingFunction: "easeInOutQuad" }
                        });
                        lastFocusedNode = nodeId;
                        
                        // Cross-component interaction: if IP, zoom Geographic map
                        if (window.geoMarkers && window.geoMarkers[nodeId]) {
                            const marker = window.geoMarkers[nodeId];
                            window.geoMapInst.setView(marker.getLatLng(), 6, { animate: true, duration: 1.0 });
                            marker.openPopup();
                        }
                    }
                } else {
                    // Clicked on empty space: zoom out to fit
                    fraudRingChartInst.fit({
                        animation: { duration: 600, easingFunction: "easeInOutQuad" }
                    });
                    lastFocusedNode = null;
                }
            });
        }
    } catch (e) { }

    // 3. Geographic Mapping
    try {
        const resGeo = await fetch(`/api/fraud_ring_map/${tx.transaction_id}`);
        const geoData = await resGeo.json();
        const mapContainer = document.getElementById('geoMap');
        
        if (window.geoMapInst) window.geoMapInst.remove();
        
        if (geoData.nodes.length === 0) {
            mapContainer.innerHTML = "<div style='padding:2rem;text-align:center;color:var(--text-muted);'>No IP geolocation data available.</div>";
            window.geoMapInst = null;
        } else {
            const primaryNode = geoData.nodes.find(n => n.is_primary) || geoData.nodes[0];
            window.geoMapInst = L.map('geoMap').setView([primaryNode.lat, primaryNode.lon], 2);
            window.geoMarkers = {};
            
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap', subdomains: 'abcd', maxZoom: 20
            }).addTo(window.geoMapInst);
            
            const latLngs = {};
            geoData.nodes.forEach(n => {
                latLngs[n.ip] = [n.lat, n.lon];
                const color = n.is_primary ? '#EF4444' : '#F59E0B';
                const circle = L.circleMarker([n.lat, n.lon], {
                    radius: n.is_primary ? 8 : 5, fillColor: color, color: color, weight: 1, opacity: 1, fillOpacity: 0.8
                }).addTo(window.geoMapInst);
                
                const popupHtml = `
                    <div style="color: #101E33; font-family: 'Inter', sans-serif; min-width: 200px;">
                        <div style="font-weight: 600; font-size: 13px; margin-bottom: 6px; border-bottom: 1px solid #E2E8F0; padding-bottom: 4px;">Node Intelligence</div>
                        <div style="font-size: 11px; line-height: 1.6;">
                            <b>IP:</b> ${n.ip}<br>
                            <b>ASN:</b> ${n.asn || 'Unknown'}<br>
                            <b>ISP:</b> ${n.isp || 'Unknown'}<br>
                            <b>Location:</b> ${n.city || 'Unknown'}, ${n.region || 'Unknown'}, ${n.country || 'Unknown'}<br>
                            <b>Coordinates:</b> ${parseFloat(n.lat).toFixed(4)}, ${parseFloat(n.lon).toFixed(4)}
                        </div>
                    </div>`;
                circle.bindPopup(popupHtml);
                
                // Zoom in when a dot is clicked
                circle.on('click', function(e) {
                    window.geoMapInst.setView(e.latlng, 6, { animate: true, duration: 1.0 });
                });
                
                window.geoMarkers[n.ip] = circle;
            });
            
            geoData.edges.forEach(e => {
                if (latLngs[e.from] && latLngs[e.to]) {
                    L.polyline([latLngs[e.from], latLngs[e.to]], { color: '#EF4444', weight: 2, opacity: 0.5, dashArray: '5, 5' }).addTo(window.geoMapInst);
                }
            });
            
            const allLatLngs = Object.values(latLngs);
            if (allLatLngs.length > 1) window.geoMapInst.fitBounds(allLatLngs, { padding: [20, 20] });
            
            setTimeout(() => {
                if (window.geoMapInst) window.geoMapInst.invalidateSize();
            }, 100);
        }
    } catch (e) { }
    
    // 4. Merchant Volume
    try {
        const resMerchant = await fetch(`/api/merchant_volume/${encodeURIComponent(tx.merchant_name)}`);
        const merchantData = await resMerchant.json();
        
        const mLabelElem = document.getElementById('merchantVolumeLabel');
        if (mLabelElem) {
            mLabelElem.innerText = `Merchant Volume - ${tx.merchant_name}`;
        }
        
        const mLabels = merchantData.map(d => d.date);
        const mCounts = merchantData.map(d => d.transaction_count);
        const currentTxDate = tx.timestamp.split(' ')[0];
        
        const mColors = mLabels.map(date => date === currentTxDate ? '#EF4444' : '#4187FF');
        
        if (merchantVolumeChartInst) merchantVolumeChartInst.destroy();
        
        const ctxM = document.getElementById('merchantVolumeChart').getContext('2d');
        merchantVolumeChartInst = new Chart(ctxM, {
            type: 'bar',
            data: { labels: mLabels, datasets: [{ label: 'Daily Volume', data: mCounts, backgroundColor: mColors, borderRadius: 4 }] },
            options: {
                responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                scales: { 
                    x: { ticks: { color: '#A8B3C7', font: { size: 9 }, maxRotation: 45, minRotation: 45 }, grid: { display: false } }, 
                    y: { ticks: { color: '#A8B3C7', font: { size: 10 } }, grid: { color: 'rgba(190,195,206,0.1)' } } 
                }
            }
        });
    } catch (e) { }
}

function streamGemmaText(fullText, btn) {
    if (gemmaTypingInterval) clearInterval(gemmaTypingInterval);
    
    explanation.innerHTML = '';
    explanation.style.fontStyle = 'normal';
    explanation.style.color = 'var(--primary-blue)';
    
    let i = 0;
    const tokens = fullText.split(/(<[^>]+>| )/);
    let currentHtml = "";
    
    gemmaTypingInterval = setInterval(() => {
        if (i >= tokens.length) {
            clearInterval(gemmaTypingInterval);
            btn.innerHTML = "✨ Ask AI";
            btn.disabled = false;
            explanation.style.color = 'var(--text-muted)';
            return;
        }
        currentHtml += tokens[i];
        explanation.innerHTML = currentHtml;
        i++;
    }, 30);
}
