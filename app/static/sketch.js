// React Input Value Setter Utility
function setReactInputValue(containerId, value) {
    const el = document.getElementById(containerId);
    if (!el) {
        console.warn("setReactInputValue: element not found:", containerId);
        return;
    }
    
    const tagName = el.tagName.toLowerCase();
    const input = (tagName === "input" || tagName === "textarea") 
        ? el 
        : (el.querySelector("input") || el.querySelector("textarea") || el.shadowRoot?.querySelector("input") || el.shadowRoot?.querySelector("textarea"));
        
    try {
        if (input) {
            const isTextarea = input.tagName.toLowerCase() === "textarea";
            const proto = isTextarea ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(proto, "value").set;
            nativeInputValueSetter.call(input, value);
        } else {
            el.value = value;
        }
        el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true, composed: true }));
        console.log(`setReactInputValue: successfully set ${containerId} to:`, value);
    } catch (e) {
        console.error(`setReactInputValue: failed to set value for ${containerId}:`, e);
    }
}

// Trigger action on Taipy Button
function clickTaipyButton(buttonId) {
    const btn = document.getElementById(buttonId);
    if (btn) {
        const clickTarget = btn.querySelector("button") || btn;
        clickTarget.click();
    }
}

// SMILES pasting bridge
async function triggerSmilesPasted() {
    const smilesVal = document.getElementById("visible_smiles_input").value;
    if (!smilesVal) {
        if (atoms.length === 0) {
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) {
                logBox.innerHTML = `<div class="checkpoint-log-line"><span class="checkpoint-time">[WARNING]</span> Please draw a molecule or enter a SMILES string to analyze.</div>`;
            }
            return;
        }
        const logBox = document.getElementById("dynamicCheckpointLogs");
        if (logBox) {
            logBox.innerHTML = `<div class="checkpoint-log-line"><span class="checkpoint-time">[INFO]</span> Molecule drawn on canvas is being analyzed automatically. Check the panels for results.</div>`;
        }
        return;
    }

    const renderButton = document.querySelector(".smiles-bar .premium-btn");
    if (renderButton) {
        renderButton.disabled = true;
        renderButton.textContent = "Loading...";
    }

    try {
        const response = await fetch("/api/analyze_smiles", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ smiles: smilesVal })
        });
        const data = await response.json();
        applyAnalysisResponse(data);
        console.log("SMILES analysis response:", data);
    } catch (e) {
        const logBox = document.getElementById("dynamicCheckpointLogs");
        if (logBox) {
            logBox.innerHTML = `<div class="checkpoint-log-line"><span class="checkpoint-time">[ERROR]</span> Failed to analyze SMILES.</div>`;
        }
        console.error("triggerSmilesPasted: request failed:", e);
    } finally {
        if (renderButton) {
            renderButton.disabled = false;
            renderButton.textContent = "Render";
        }
    }
}

// Chat prompts bridge — posts directly to /api/chat
async function triggerChatSend() {
    const chatVal = document.getElementById("visible_chat_prompt").value.trim();
    if (!chatVal) return;

    const sendBtn = document.querySelector(".chat-input-bar .premium-btn");
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = "Sending..."; }

    const chatLog = document.getElementById("dynamicChatLog");
    if (chatLog) {
        const msg = document.createElement("div");
        msg.className = "chat-message message-user";
        msg.textContent = chatVal;
        chatLog.appendChild(msg);
        document.getElementById("chatMessages").scrollTop = 99999;
    }
    document.getElementById("visible_chat_prompt").value = "";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: chatVal })
        });
        const data = await response.json();
        if (chatLog) {
            const reply = document.createElement("div");
            reply.className = "chat-message message-system";
            reply.textContent = data.ok
                ? (data.command ? `PyMOL: ${data.command}` : "No command generated.")
                : `Error: ${data.error}`;
            chatLog.appendChild(reply);
            document.getElementById("chatMessages").scrollTop = 99999;
        }
    } catch (e) {
        if (chatLog) {
            const err = document.createElement("div");
            err.className = "chat-message message-system";
            err.textContent = "Connection error. Is the server running?";
            chatLog.appendChild(err);
        }
        console.error("triggerChatSend failed:", e);
    } finally {
        if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = "Send"; }
    }
}

// Apply full analysis API response to the UI
function applyAnalysisResponse(data) {
    if (!data) return;
    if (data.canvas_payload && data.canvas_payload.atoms) {
        loadCanvasData(data.canvas_payload);
    }
    if (typeof data.predictions_html === "string") {
        document.getElementById("dynamicPredictions").innerHTML = data.predictions_html;
    }
    if (typeof data.repurposing_html === "string") {
        document.getElementById("dynamicRepurposing").innerHTML = data.repurposing_html;
    }
    if (typeof data.checkpoint_logs_html === "string") {
        const cpLogs = document.getElementById("dynamicCheckpointLogs");
        cpLogs.innerHTML = data.checkpoint_logs_html;
        const cpBody = document.getElementById("checkpointBody");
        if (cpBody) cpBody.scrollTop = cpBody.scrollHeight;
    }
}

// Setup Canvas size on load
window.addEventListener('load', () => {
    canvas = document.getElementById("molCanvas");
    if (canvas) {
        ctx = canvas.getContext("2d");
        resizeCanvas();
        panX = canvas.width / 2;
        panY = canvas.height / 2;
        drawGrid();
    }
    // Initialize history stack
    initHistory();
});

// ==========================================
// 2D Molecular Sketcher Canvas Engine (HTML5)
// ==========================================
let canvas = document.getElementById("molCanvas");
let ctx = canvas ? canvas.getContext("2d") : null;
let activeMode = "draw"; // "draw", "move", "erase"
let activeElement = "C";
let activeBondType = 1; // 1, 2, 3
let atoms = [];
let bonds = [];
let nextAtomId = 1;

let lastSentPayload = "";

// Zoom & Pan state
let zoomLevel = 1.0;
let panX = 0;
let panY = 0;
let isPanning = false;
let panStartX = 0;
let panStartY = 0;

// Dragging & Interaction variables
let selectedAtom = null;
let hoveredAtom = null;
let hoveredBond = null; // Phase 1.2
let dragStartAtom = null;
let isDragging = false;
let dragX = 0;
let dragY = 0;
let snapGrid = 15;

// Phase 1.1: Undo/Redo History Stack state
let historyStack = [];
let historyIndex = -1;
const MAX_HISTORY = 80;

// Custom curated harmonized CPK Colors matching Inter dark elements
const elementColors = {
    'C': '#6B7280',
    'O': '#DC2626',
    'N': '#2563EB',
    'H': '#9CA3AF',
    'P': '#EA580C',
    'S': '#CA8A04'
};

const atomRadius = 14;

// Convert screen coords to world coords (accounting for zoom/pan)
function screenToWorld(sx, sy) {
    return {
        x: (sx - panX) / zoomLevel,
        y: (sy - panY) / zoomLevel
    };
}

function resizeCanvas() {
    const container = document.getElementById("canvasContainer");
    if (!container || !canvas) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    redraw();
}

window.addEventListener('resize', resizeCanvas);

// Zoom indicator update
function updateZoomIndicator() {
    const el = document.getElementById("zoomIndicator");
    if (el) el.textContent = Math.round(zoomLevel * 100) + "%";
}

function setMode(mode) {
    activeMode = mode;
    document.getElementById("btnDraw").classList.toggle("active", mode === "draw");
    document.getElementById("btnMove").classList.toggle("active", mode === "move");
    document.getElementById("btnErase").classList.toggle("active", mode === "erase");
}

function setActiveElement(el, btn) {
    activeElement = el;
    document.querySelectorAll(".left-rail .rail-btn-element").forEach(b => {
        b.classList.remove("active-element");
    });
    btn.classList.add("active-element");
}

function setBondType(type) {
    activeBondType = type;
    document.getElementById("btnBond1").classList.toggle("active", type === 1);
    document.getElementById("btnBond2").classList.toggle("active", type === 2);
    document.getElementById("btnBond3").classList.toggle("active", type === 3);
}

function clearCanvas() {
    atoms = [];
    bonds = [];
    nextAtomId = 1;
    saveSnapshot();
    redraw();
    pushPayload();
}

// Find atom at (x, y) coordinates
function getAtomAt(x, y) {
    return atoms.find(atom => {
        const dist = Math.hypot(atom.x - x, atom.y - y);
        return dist < atomRadius + 6;
    }) || null;
}

// Phase 1.2: Find bond at (x, y) coordinates
function getBondAt(x, y) {
    let closestBond = null;
    let minDist = Math.max(5, Math.min(25, 10 / zoomLevel));
    bonds.forEach(bond => {
        const a1 = atoms.find(a => a.id === bond.source);
        const a2 = atoms.find(a => a.id === bond.target);
        if (!a1 || !a2) return;
        const dist = distToSegment({ x, y }, a1, a2);
        if (dist < minDist) {
            minDist = dist;
            closestBond = bond;
        }
    });
    return closestBond;
}

// Phase 1.2: Cycle bond type (1 -> 2 -> 3 -> 1)
function cycleBondType(bond) {
    bond.type = bond.type === 1 ? 2 : bond.type === 2 ? 3 : 1;
}

// Draw coordinate grid (in screen space, independent of zoom)
function drawGrid() {
    if (!ctx || !canvas) return;
    ctx.save();
    ctx.strokeStyle = "rgba(0, 0, 0, 0.04)";
    ctx.lineWidth = 1;
    const gridSz = 40;
    for (let x = (panX % gridSz + gridSz) % gridSz; x < canvas.width; x += gridSz) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = (panY % gridSz + gridSz) % gridSz; y < canvas.height; y += gridSz) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }
    ctx.restore();
}

// Main redraw function — applies zoom/pan transform for molecule rendering
function redraw() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawGrid();

    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoomLevel, zoomLevel);

    // 1. Draw Bonds
    bonds.forEach(bond => {
        const a1 = atoms.find(a => a.id === bond.source);
        const a2 = atoms.find(a => a.id === bond.target);
        if (!a1 || !a2) return;

        const isHovered = hoveredBond && hoveredBond.source === bond.source && hoveredBond.target === bond.target;
        ctx.strokeStyle = isHovered ? (activeMode === "erase" ? "#EF4444" : "#2563EB") : "#94A3B8";
        ctx.lineWidth = (isHovered ? 4 : 2.5) / zoomLevel;

        const angle = Math.atan2(a2.y - a1.y, a2.x - a1.x);
        const offset_x = Math.sin(angle) * 5;
        const offset_y = Math.cos(angle) * 5;

        if (bond.type === 1) {
            ctx.beginPath(); ctx.moveTo(a1.x, a1.y); ctx.lineTo(a2.x, a2.y); ctx.stroke();
        } else if (bond.type === 2) {
            ctx.beginPath();
            ctx.moveTo(a1.x - offset_x, a1.y + offset_y);
            ctx.lineTo(a2.x - offset_x, a2.y + offset_y);
            ctx.moveTo(a1.x + offset_x, a1.y - offset_y);
            ctx.lineTo(a2.x + offset_x, a2.y - offset_y);
            ctx.stroke();
        } else if (bond.type === 3) {
            ctx.beginPath();
            ctx.moveTo(a1.x, a1.y); ctx.lineTo(a2.x, a2.y);
            ctx.moveTo(a1.x - offset_x * 1.5, a1.y + offset_y * 1.5);
            ctx.lineTo(a2.x - offset_x * 1.5, a2.y + offset_y * 1.5);
            ctx.moveTo(a1.x + offset_x * 1.5, a1.y - offset_y * 1.5);
            ctx.lineTo(a2.x + offset_x * 1.5, a2.y - offset_y * 1.5);
            ctx.stroke();
        }

        // Midpoint circle highlight for bond toggling
        if (isHovered && activeMode === "draw") {
            ctx.fillStyle = "#2563EB";
            ctx.beginPath();
            ctx.arc((a1.x + a2.x) / 2, (a1.y + a2.y) / 2, 4.5 / zoomLevel, 0, Math.PI * 2);
            ctx.fill();
        }
    });

    // Draw active bond preview while dragging
    if (activeMode === "draw" && isDragging && dragStartAtom) {
        const worldDrag = screenToWorld(dragX, dragY);
        ctx.strokeStyle = "rgba(37, 99, 235, 0.5)";
        ctx.lineWidth = 2 / zoomLevel;
        ctx.setLineDash([5 / zoomLevel, 5 / zoomLevel]);
        ctx.beginPath();
        ctx.moveTo(dragStartAtom.x, dragStartAtom.y);
        ctx.lineTo(worldDrag.x, worldDrag.y);
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // 2. Draw Atoms
    const scaledRadius = atomRadius;
    atoms.forEach(atom => {
        const color = elementColors[atom.element] || '#ffffff';
        const isHovered = hoveredAtom && hoveredAtom.id === atom.id;

        ctx.fillStyle = "#FFFFFF";
        ctx.strokeStyle = isHovered ? "#2563EB" : "#D1D5DB";
        ctx.lineWidth = (isHovered ? 2 : 1) / zoomLevel;
        ctx.beginPath();
        ctx.arc(atom.x, atom.y, scaledRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        if (isHovered) { ctx.shadowColor = "rgba(37,99,235,0.35)"; ctx.shadowBlur = 8; }

        ctx.fillStyle = color;
        ctx.font = `bold ${13}px 'Inter', sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(atom.element, atom.x, atom.y);
        ctx.shadowBlur = 0;
    });

    ctx.restore();
    updateUndoRedoButtons();
    updateZoomIndicator();
}

// Handle mouse canvas actions — all coordinates converted to world space
if (canvas) {
    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const delta = e.deltaY < 0 ? 1.1 : 0.9;
        const newZoom = Math.max(0.2, Math.min(5.0, zoomLevel * delta));
        panX = mx - (mx - panX) * (newZoom / zoomLevel);
        panY = my - (my - panY) * (newZoom / zoomLevel);
        zoomLevel = newZoom;
        redraw();
    }, { passive: false });

    canvas.addEventListener('mousedown', (e) => {
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const { x, y } = screenToWorld(sx, sy);

        if (e.button === 1) { e.preventDefault(); isPanning = true; panStartX = sx - panX; panStartY = sy - panY; return; }

        const clickedAtom = getAtomAt(x, y);

        if (activeMode === "draw") {
            if (clickedAtom) {
                dragStartAtom = clickedAtom; isDragging = true; dragX = sx; dragY = sy;
            } else {
                // Check in-place bond order toggling first
                const clickedBond = getBondAt(x, y);
                if (clickedBond) {
                    cycleBondType(clickedBond);
                    saveSnapshot();
                    redraw();
                    pushPayload();
                    return;
                }
                const snap = snapGrid;
                atoms.push({ id: nextAtomId++, x: Math.round(x / snap) * snap, y: Math.round(y / snap) * snap, element: activeElement });
                saveSnapshot();
                redraw(); pushPayload();
            }
        } else if (activeMode === "move") {
            if (clickedAtom) { selectedAtom = clickedAtom; isDragging = true; }
            else { isPanning = true; panStartX = sx - panX; panStartY = sy - panY; }
        } else if (activeMode === "erase") {
            if (clickedAtom) {
                atoms = atoms.filter(a => a.id !== clickedAtom.id);
                bonds = bonds.filter(b => b.source !== clickedAtom.id && b.target !== clickedAtom.id);
                saveSnapshot();
                redraw(); pushPayload();
            } else {
                const oldBondCount = bonds.length;
                bonds = bonds.filter(bond => {
                    const a1 = atoms.find(a => a.id === bond.source);
                    const a2 = atoms.find(a => a.id === bond.target);
                    if (!a1 || !a2) return true;
                    return distToSegment({x, y}, a1, a2) > 8;
                });
                if (bonds.length !== oldBondCount) {
                    saveSnapshot();
                }
                redraw(); pushPayload();
            }
        }
    });

    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const { x, y } = screenToWorld(sx, sy);

        if (isPanning) {
            panX = sx - panStartX;
            panY = sy - panStartY;
            redraw(); return;
        }

        const oldHoverAtom = hoveredAtom;
        hoveredAtom = getAtomAt(x, y);

        const oldHoverBond = hoveredBond;
        if (!hoveredAtom && (activeMode === "draw" || activeMode === "erase")) {
            hoveredBond = getBondAt(x, y);
        } else {
            hoveredBond = null;
        }

        if (oldHoverAtom !== hoveredAtom || oldHoverBond !== hoveredBond) redraw();

        if (isDragging) {
            if (activeMode === "draw") {
                dragX = sx; dragY = sy; redraw();
            } else if (activeMode === "move" && selectedAtom) {
                const snap = snapGrid;
                selectedAtom.x = Math.round(x / snap) * snap;
                selectedAtom.y = Math.round(y / snap) * snap;
                redraw();
            }
        }
    });

    canvas.addEventListener('mouseup', (e) => {
        if (isPanning) { isPanning = false; return; }
        if (!isDragging) return;
        isDragging = false;

        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const { x, y } = screenToWorld(sx, sy);

        if (activeMode === "draw" && dragStartAtom) {
            const targetAtom = getAtomAt(x, y);
            if (targetAtom && targetAtom.id !== dragStartAtom.id) {
                const existingBond = bonds.find(b =>
                    (b.source === dragStartAtom.id && b.target === targetAtom.id) ||
                    (b.source === targetAtom.id && b.target === dragStartAtom.id)
                );
                let changed = false;
                if (existingBond) {
                    if (existingBond.type !== activeBondType) {
                        existingBond.type = activeBondType;
                        changed = true;
                    }
                } else {
                    bonds.push({ source: dragStartAtom.id, target: targetAtom.id, type: activeBondType });
                    changed = true;
                }
                if (changed) {
                    saveSnapshot();
                    pushPayload();
                }
            }
            dragStartAtom = null;
        }
        if (activeMode === "move" && selectedAtom) { 
            selectedAtom = null; 
            saveSnapshot();
            pushPayload(); 
        }
        redraw();
    });

    canvas.addEventListener('mouseleave', () => { isPanning = false; });
}

// Math utilities for bond click-erasure
function dist2(v, w) { return (v.x - w.x)**2 + (v.y - w.y)**2; }
function distToSegmentSquared(p, v, w) {
    const l2 = dist2(v, w);
    if (l2 === 0) return dist2(p, v);
    let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
    t = Math.max(0, Math.min(1, t));
    return dist2(p, { x: v.x + t * (w.x - v.x), y: v.y + t * (w.y - v.y) });
}
function distToSegment(p, v, w) { return Math.sqrt(distToSegmentSquared(p, v, w)); }

// PUSH payload - stores locally and triggers live ADME descriptors check
function pushPayload() {
    const payload = {
        atoms: atoms.map(a => ({ id: a.id, x: a.x, y: a.y, element: a.element })),
        bonds: bonds.map(b => ({ source: b.source, target: b.target, type: b.type }))
    };
    lastSentPayload = JSON.stringify(payload);
    triggerDebouncedADME(); // Phase 4 live update
}

// Fit all atoms into view with nice padding
function fitToView() {
    if (!canvas || atoms.length === 0) {
        zoomLevel = 1.0; panX = 0; panY = 0; redraw(); return;
    }
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    atoms.forEach(a => {
        if (a.x < minX) minX = a.x; if (a.x > maxX) maxX = a.x;
        if (a.y < minY) minY = a.y; if (a.y > maxY) maxY = a.y;
    });
    const pad = 80;
    const molW = maxX - minX || 1;
    const molH = maxY - minY || 1;
    const scaleX = (canvas.width - pad * 2) / molW;
    const scaleY = (canvas.height - pad * 2) / molH;
    zoomLevel = Math.max(0.3, Math.min(4.0, Math.min(scaleX, scaleY)));
    const molCX = (minX + maxX) / 2;
    const molCY = (minY + maxY) / 2;
    panX = canvas.width / 2 - molCX * zoomLevel;
    panY = canvas.height / 2 - molCY * zoomLevel;
    redraw();
}

// LOAD canvas data from Backend (from pasted SMILES — raw RDKit Angstrom coords)
function loadCanvasData(data) {
    if (!data || !data.atoms) return;
    atoms = [];
    bonds = [];

    if (data.atoms.length === 0) { redraw(); return; }

    data.atoms.forEach(a => {
        atoms.push({
            id: a.id,
            x: a.x,
            y: -a.y,
            element: a.element
        });
    });

    if (data.bonds) {
        data.bonds.forEach(b => {
            bonds.push({ source: b.source, target: b.target, type: b.type });
        });
    }

    nextAtomId = Math.max(...atoms.map(a => a.id), 0) + 1;

    fitToView();
    saveSnapshot(); // Save the newly loaded molecule layout to the undo/redo stack
    console.log("Canvas loaded from RDKit backend:", atoms.length, "atoms,", bonds.length, "bonds");
    triggerDebouncedADME(); // Evaluate ADME for the loaded structure
}

// ==========================================
// Phase 1.1: Undo/Redo History Stack Logic
// ==========================================
function initHistory() {
    historyStack = [JSON.stringify({ atoms: [], bonds: [], nextAtomId: 1 })];
    historyIndex = 0;
    updateUndoRedoButtons();
}

function saveSnapshot() {
    const snapshot = JSON.stringify({ atoms, bonds, nextAtomId });
    if (historyIndex < historyStack.length - 1) {
        historyStack = historyStack.slice(0, historyIndex + 1);
    }
    historyStack.push(snapshot);
    if (historyStack.length > MAX_HISTORY) {
        historyStack.shift();
    }
    historyIndex = historyStack.length - 1;
    updateUndoRedoButtons();
}

function undo() {
    if (historyIndex > 0) {
        historyIndex--;
        restoreSnapshot(historyStack[historyIndex]);
        redraw();
        pushPayload();
    }
}

function redo() {
    if (historyIndex < historyStack.length - 1) {
        historyIndex++;
        restoreSnapshot(historyStack[historyIndex]);
        redraw();
        pushPayload();
    }
}

function restoreSnapshot(snapshotStr) {
    try {
        const state = JSON.parse(snapshotStr);
        atoms = JSON.parse(JSON.stringify(state.atoms || []));
        bonds = JSON.parse(JSON.stringify(state.bonds || []));
        nextAtomId = state.nextAtomId || 1;
        updateUndoRedoButtons();
    } catch (e) {
        console.error("restoreSnapshot: failed to restore state:", e);
    }
}

function updateUndoRedoButtons() {
    const btnUndo = document.getElementById("btnUndo");
    const btnRedo = document.getElementById("btnRedo");
    if (btnUndo) {
        btnUndo.disabled = (historyIndex <= 0);
    }
    if (btnRedo) {
        btnRedo.disabled = (historyIndex >= historyStack.length - 1);
    }
}

document.addEventListener('keydown', e => {
    const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
    if (activeTag === "input" || activeTag === "textarea") {
        return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
        e.preventDefault();
        redo();
    }
});

// ==========================================
// Phase 1.3: Structural Ring Templates
// ==========================================
const RING_TEMPLATES = {
    benzene: {
        atoms: 6, elements: ['C','C','C','C','C','C'],
        bonds: [[0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,5,2],[5,0,1]],
        radius: 40
    },
    cyclohexane: {
        atoms: 6, elements: ['C','C','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]],
        radius: 40
    },
    cyclopentane: {
        atoms: 5, elements: ['C','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,0,1]],
        radius: 35
    },
    pyridine: {
        atoms: 6, elements: ['C','C','C','C','C','N'],
        bonds: [[0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,5,2],[5,0,1]],
        radius: 40
    }
};

function injectRingTemplate(templateName) {
    const tmpl = RING_TEMPLATES[templateName];
    if (!tmpl) return;
    
    let centerX = 0;
    let centerY = 0;
    if (canvas) {
        const worldCenter = screenToWorld(canvas.width / 2, canvas.height / 2);
        centerX = worldCenter.x;
        centerY = worldCenter.y;
    }
    
    const angleStep = (2 * Math.PI) / tmpl.atoms;
    const idMap = {};
    
    tmpl.elements.forEach((elem, i) => {
        const angle = i * angleStep - Math.PI / 2;
        const id = nextAtomId++;
        idMap[i] = id;
        atoms.push({
            id: id,
            x: Math.round((centerX + Math.cos(angle) * tmpl.radius) / 5) * 5,
            y: Math.round((centerY + Math.sin(angle) * tmpl.radius) / 5) * 5,
            element: elem
        });
    });
    
    tmpl.bonds.forEach(([s, t, type]) => {
        bonds.push({ source: idMap[s], target: idMap[t], type });
    });
    
    saveSnapshot();
    redraw();
    pushPayload();
}

// ==========================================
// Phase 2.1: Automated 2D Geometry Optimization
// ==========================================
async function triggerOptimize2D() {
    if (atoms.length === 0) return;
    
    const btn = document.getElementById("btnOptimize");
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="font-size:11px;"></i>';
    
    const payload = {
        atoms: atoms.map(a => ({ id: a.id, x: a.x, y: a.y, element: a.element })),
        bonds: bonds.map(b => ({ source: b.source, target: b.target, type: b.type }))
    };
    
    try {
        const response = await fetch("/api/optimize_2d", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.ok && data.canvas_payload) {
            loadCanvasData(data.canvas_payload);
            
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) {
                logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[RDKIT]</span> Geometry optimization complete. Textbook coords generated.</div>`;
                document.getElementById("checkpointBody").scrollTop = 99999;
            }
        }
    } catch (e) {
        console.error("2D optimization request failed:", e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
}

// ==========================================
// Phase 4: Real-Time ADME Dashboard
// ==========================================
let admeTimeout = null;

function triggerDebouncedADME() {
    if (admeTimeout) clearTimeout(admeTimeout);
    admeTimeout = setTimeout(runADMEEvaluation, 800);
}

async function getActiveSmiles() {
    const inputVal = document.getElementById("visible_smiles_input").value.trim();
    if (inputVal) return inputVal;
    
    const payload = {
        atoms: atoms.map(a => ({ id: a.id, x: a.x, y: a.y, element: a.element })),
        bonds: bonds.map(b => ({ source: b.source, target: b.target, type: b.type }))
    };
    if (payload.atoms.length === 0) return "";
    
    try {
        const res = await fetch("/api/canvas_to_smiles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.ok && data.smiles) {
            return data.smiles;
        }
    } catch (e) {
        console.error("getActiveSmiles failed to derive SMILES:", e);
    }
    return "";
}

async function runADMEEvaluation() {
    const smiles = await getActiveSmiles();
    const admeDiv = document.getElementById("dynamicADME");
    
    if (!smiles) {
        if (admeDiv) {
            admeDiv.innerHTML = `<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic;'>Draw a molecule to live-calculate ADME descriptors.</div>`;
        }
        return;
    }
    
    try {
        const res = await fetch("/api/descriptors", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ smiles })
        });
        const data = await res.json();
        if (data.ok) {
            renderADMEProfile(data);
        }
    } catch (e) {
        console.error("runADMEEvaluation error:", e);
    }
}

function renderADMEProfile(data) {
    const admeDiv = document.getElementById("dynamicADME");
    if (!admeDiv) return;
    
    const lipinskiStatus = data.lipinski_pass 
        ? `<span style="color:#059669; font-weight:700;"><i class="fa-solid fa-circle-check"></i> Lipinski Pass</span>` 
        : `<span style="color:#DC2626; font-weight:700;"><i class="fa-solid fa-triangle-exclamation"></i> Lipinski Fail (${data.lipinski_violations} violations)</span>`;
        
    const veberStatus = data.veber_pass 
        ? `<span style="color:#059669; font-weight:700;"><i class="fa-solid fa-circle-check"></i> Veber Pass</span>` 
        : `<span style="color:#D97706; font-weight:700;"><i class="fa-solid fa-triangle-exclamation"></i> Veber Fail</span>`;

    const getProgressColor = (pass, borderline) => {
        if (pass) return "#059669";
        if (borderline) return "#D97706";
        return "#DC2626";
    };

    const mwPercent = Math.min(100, (data.mw / 600) * 100);
    const mwColor = getProgressColor(data.mw_pass, data.mw > 450 && data.mw <= 500);

    const logPPercent = Math.min(100, Math.max(0, ((data.logp + 3) / 10) * 100));
    const logPColor = getProgressColor(data.logp_pass, data.logp > 4 && data.logp <= 5);

    const hbdPercent = Math.min(100, (data.hbd / 8) * 100);
    const hbdColor = getProgressColor(data.hbd_pass, data.hbd === 5);

    const hbaPercent = Math.min(100, (data.hba / 15) * 100);
    const hbaColor = getProgressColor(data.hba_pass, data.hba === 10);

    const tpsaPercent = Math.min(100, (data.tpsa / 180) * 100);
    const tpsaColor = getProgressColor(data.tpsa_pass, data.tpsa > 120 && data.tpsa <= 140);

    const rbPercent = Math.min(100, (data.rotatable_bonds / 15) * 100);
    const rbColor = getProgressColor(data.rb_pass, data.rotatable_bonds === 10);

    admeDiv.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.6rem; background:var(--bg-hover); border-radius:var(--radius-md); font-size:0.75rem; border:1px solid var(--border-primary); margin-bottom:0.5rem;">
            <div>${lipinskiStatus}</div>
            <div style="height:12px; width:1px; background:var(--border-primary);"></div>
            <div>${veberStatus}</div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; font-size:0.72rem; color:var(--text-secondary); margin-bottom:0.5rem;">
            <div>Formula: <strong style="color:var(--text-primary); font-family:'JetBrains Mono',monospace;">${data.molecular_formula}</strong></div>
            <div>Heavy Atoms: <strong style="color:var(--text-primary);">${data.heavy_atom_count}</strong></div>
            <div style="grid-column: span 2;">Rings: <strong style="color:var(--text-primary);">${data.ring_count} (${data.aromatic_ring_count} aromatic)</strong></div>
        </div>

        <div style="display:flex; flex-direction:column; gap:0.6rem;">
            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">Molecular Weight</span>
                    <span><strong style="color:var(--text-primary);">${data.mw}</strong> g/mol <i class="${data.mw_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${mwPercent}%; height:100%; background:${mwColor}; border-radius:2px;"></div>
                </div>
            </div>

            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">Partition Coeff (LogP)</span>
                    <span><strong style="color:var(--text-primary);">${data.logp}</strong> <i class="${data.logp_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${logPPercent}%; height:100%; background:${logPColor}; border-radius:2px;"></div>
                </div>
            </div>

            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">H-Bond Donors</span>
                    <span><strong style="color:var(--text-primary);">${data.hbd}</strong> <i class="${data.hbd_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${hbdPercent}%; height:100%; background:${hbdColor}; border-radius:2px;"></div>
                </div>
            </div>

            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">H-Bond Acceptors</span>
                    <span><strong style="color:var(--text-primary);">${data.hba}</strong> <i class="${data.hba_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${hbaPercent}%; height:100%; background:${hbaColor}; border-radius:2px;"></div>
                </div>
            </div>

            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">Polar Surface Area (TPSA)</span>
                    <span><strong style="color:var(--text-primary);">${data.tpsa}</strong> Å² <i class="${data.tpsa_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${tpsaPercent}%; height:100%; background:${tpsaColor}; border-radius:2px;"></div>
                </div>
            </div>

            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:0.15rem;">
                    <span style="color:var(--text-secondary);">Rotatable Bonds</span>
                    <span><strong style="color:var(--text-primary);">${data.rotatable_bonds}</strong> <i class="${data.rb_pass ? 'fa-solid fa-check text-green' : 'fa-solid fa-xmark text-red'}"></i></span>
                </div>
                <div style="width:100%; height:4px; background:#E2E8F0; border-radius:2px; overflow:hidden;">
                    <div style="width:${rbPercent}%; height:100%; background:${rbColor}; border-radius:2px;"></div>
                </div>
            </div>
        </div>
    `;
}

// ==========================================
// Phase 3: PDB Target & Interaction Profiling
// ==========================================
let activePdbId = "";
let activeLigands = [];

async function fetchPdbTarget() {
    const pdbIdInput = document.getElementById("pdbIdInput").value.trim();
    if (!pdbIdInput) {
        alert("Please enter a valid 4-character PDB ID.");
        return;
    }
    
    const btn = document.querySelector(".pdb-bar button");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Loading...";
    
    try {
        const res = await fetch(`/api/pdb/fetch?pdb_id=${pdbIdInput}`);
        const data = await res.json();
        if (data.ok) {
            activePdbId = data.pdb_id;
            activeLigands = data.ligands;
            populateLigandSelect(data.ligands);
            
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) {
                logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[PDB]</span> Loaded structure ${activePdbId} successfully. Found ${activeLigands.length} ligands.</div>`;
                document.getElementById("checkpointBody").scrollTop = 99999;
            }
        } else {
            alert("Error: " + data.error);
        }
    } catch (e) {
        console.error("fetchPdbTarget error:", e);
        alert("Failed to fetch PDB target.");
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function uploadPdbFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const res = await fetch("/api/pdb/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.ok) {
            activePdbId = data.filename.split(".")[0].toUpperCase().substring(0, 4);
            activeLigands = data.ligands;
            populateLigandSelect(data.ligands);
            
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) {
                logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[PDB]</span> Uploaded ${data.filename} successfully. Found ${activeLigands.length} ligands.</div>`;
                document.getElementById("checkpointBody").scrollTop = 99999;
            }
        } else {
            alert("Upload error: " + data.error);
        }
    } catch (e) {
        console.error("uploadPdbFile error:", e);
        alert("Failed to upload PDB file.");
    }
}

function populateLigandSelect(ligands) {
    const select = document.getElementById("ligandSelect");
    const wrapper = document.getElementById("ligandSelectWrapper");
    if (!select || !wrapper) return;
    
    select.innerHTML = '<option value="">-- Choose --</option>';
    ligands.forEach((lig, idx) => {
        const optVal = `${lig.resname}|${lig.chain}|${lig.seq}`;
        const optText = `${lig.resname} (${lig.chain}:${lig.seq})`;
        const opt = document.createElement("option");
        opt.value = optVal;
        opt.textContent = optText;
        select.appendChild(opt);
    });
    
    wrapper.style.display = "flex";
}

async function computeInteractions() {
    const select = document.getElementById("ligandSelect");
    if (!select || !select.value) {
        alert("Please select a ligand residue first.");
        return;
    }
    
    const smiles = await getActiveSmiles();
    if (!smiles) {
        alert("Please enter a SMILES or draw a molecule on the canvas first.");
        return;
    }
    
    const [resname, chain, seq] = select.value.split("|");
    
    const btn = document.querySelector("#ligandSelectWrapper button");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Profiling...";
    
    const svgContainer = document.getElementById("interactionDiagramContainer");
    if (svgContainer) {
        svgContainer.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-tertiary); padding:2rem; text-align:center;">
                <i class="fa-solid fa-spinner fa-spin" style="font-size:32px; margin-bottom:1rem; color:var(--accent-blue);"></i>
                <div style="font-weight:600; margin-bottom:0.25rem;">Computing non-covalent binding profile...</div>
                <div style="font-size:0.75rem;">Evaluating hydrogen bonds, pi-stacking, salt bridges, and hydrophobic contacts in PDB space.</div>
            </div>
        `;
    }
    
    try {
        const response = await fetch("/api/interactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                smiles: smiles,
                pdb_id: activePdbId,
                ligand_resname: resname,
                ligand_chain: chain,
                ligand_seq: seq
            })
        });
        const data = await response.json();
        if (data.ok) {
            renderInteractionDiagram(data.interactions, data.ligand_2d_coords);
            
            const dlBtn = document.getElementById("btnDownloadSVG");
            if (dlBtn) dlBtn.style.display = "flex";
            
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) {
                logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[PROFILE]</span> Found ${data.interactions.length} non-covalent interactions in binding pocket.</div>`;
                document.getElementById("checkpointBody").scrollTop = 99999;
            }
        } else {
            alert("Profiling error: " + data.error);
        }
    } catch (e) {
        console.error("computeInteractions error:", e);
        alert("Failed to compute interactions.");
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// ==========================================
// Phase 3.3: Tab Switching Logic
// ==========================================
function switchMainTab(tab) {
    const tabSketcher = document.getElementById("tabSketcher");
    const tabInteractions = document.getElementById("tabInteractions");
    const canvasContainer = document.getElementById("canvasContainer");
    const interactionViewContainer = document.getElementById("interactionViewContainer");
    const smilesBar = document.querySelector(".smiles-bar");
    const leftRail = document.querySelector(".left-rail");
    
    if (tab === "sketcher") {
        tabSketcher.classList.add("active");
        tabInteractions.classList.remove("active");
        canvasContainer.style.display = "block";
        interactionViewContainer.style.display = "none";
        if (smilesBar) smilesBar.style.display = "flex";
        if (leftRail) leftRail.style.display = "flex";
        resizeCanvas();
    } else {
        tabSketcher.classList.remove("active");
        tabInteractions.classList.add("active");
        canvasContainer.style.display = "none";
        interactionViewContainer.style.display = "flex";
        if (smilesBar) smilesBar.style.display = "none";
        if (leftRail) leftRail.style.display = "none";
    }
}