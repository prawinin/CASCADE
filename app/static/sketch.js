// ── Action Logger ──────────────────────────────────────────────────
let _actionSessionId = null;

async function initActionLogger() {
    try {
        const res = await fetch("/api/action_log/start", { method: "POST" });
        const data = await res.json();
        _actionSessionId = data.session_id;
    } catch (e) { /* silent */ }
}

function logAction(actionType, actionData) {
    if (!_actionSessionId) return;
    fetch("/api/action_log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            action: actionType,
            data: actionData,
            session_id: _actionSessionId
        })
    }).catch(() => {});  // Fire and forget
}

document.addEventListener("DOMContentLoaded", initActionLogger);

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
        if (data.ok) {
            try {
                const sdfRes = await fetch("/static/molecule.sdf");
                const sdfData = await sdfRes.text();
                render3DModel(sdfData);
            } catch (err) {
                console.error("Failed to fetch molecule.sdf for 3D render:", err);
            }
        }
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
                ? (data.command ? `Applied: ${data.command}` : "No command generated.")
                : `Error: ${data.error}`;
            chatLog.appendChild(reply);
            document.getElementById("chatMessages").scrollTop = 99999;
        }
        // Apply the generated commands to the live 3Dmol.js viewer
        if (data.ok && data.command) {
            applyPyMOLTo3Dmol(data.command);
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

// ==========================================
// PyMOL Command → 3Dmol.js Live Translator
// ==========================================
function applyPyMOLTo3Dmol(commandText) {
    if (!glViewer) {
        console.warn("applyPyMOLTo3Dmol: 3D viewer not initialised yet.");
        return;
    }

    const lines = commandText.toLowerCase().split("\n").map(l => l.trim()).filter(Boolean);
    let styled = false;

    for (const line of lines) {
        // ── Representation style ──────────────────────────────────────────────
        if (line.startsWith("show stick") || line === "show sticks") {
            glViewer.setStyle({}, { stick: { colorscheme: "Jmol", radius: 0.16 }, sphere: { colorscheme: "Jmol", scale: 0.28 } });
            styled = true;
        } else if (line.startsWith("show sphere") || line === "show spheres") {
            glViewer.setStyle({}, { sphere: { colorscheme: "Jmol", scale: 0.8 } });
            styled = true;
        } else if (line.startsWith("show cartoon") || line === "show cartoon") {
            glViewer.setStyle({}, { cartoon: { colorscheme: "Jmol" }, stick: { colorscheme: "Jmol", radius: 0.1 } });
            styled = true;
        } else if (line.startsWith("show line") || line === "show lines") {
            glViewer.setStyle({}, { line: { colorscheme: "Jmol", linewidth: 1.5 } });
            styled = true;
        } else if (line.startsWith("hide")) {
            glViewer.setStyle({}, {});
            styled = true;

        // ── Colour commands ───────────────────────────────────────────────────
        } else if (line.startsWith("color ") || line.startsWith("colour ") || line.includes("color ") || line.includes("colour ")) {
            // Handles both standard ("color green, elem c") and compound LLM styles ("color atom 1, red color atom 2, blue...")
            const colorsList = ["red", "green", "blue", "yellow", "orange", "purple", "cyan", "magenta", "white", "black", "grey", "gray", "pink", "brown", "violet"];
            const cleanLine = line.startsWith("color") || line.startsWith("colour") ? line : "color " + line;
            const subparts = cleanLine.split(/colou?r\s+/).map(p => p.trim()).filter(Boolean);
            
            for (const part of subparts) {
                let colour = "cyan";
                const words = part.split(/[\s,]+/).map(w => w.trim().toLowerCase());
                for (const w of words) {
                    if (colorsList.includes(w) || w.startsWith("#")) {
                        colour = w;
                        break;
                    }
                }
                
                const elemMatch = part.match(/elem\s+(\w+)/i);
                const idMatch = part.match(/(?:atom|id|index|serial)\s+(\d+)/i) || part.match(/\b(\d+)\b/);
                
                let selector = {};
                if (elemMatch) {
                    selector = { elem: elemMatch[1].toUpperCase() };
                } else if (idMatch) {
                    selector = { serial: parseInt(idMatch[1], 10) };
                }
                
                glViewer.setStyle(selector, { 
                    stick: { color: colour, radius: 0.16 }, 
                    sphere: { color: colour, scale: 0.28 } 
                });
            }
            styled = true;

        // ── Background colour ─────────────────────────────────────────────────
        } else if (line.startsWith("bg_color ") || line.startsWith("bg_colour ")) {
            const bg = line.split(/\s+/)[1] || "black";
            glViewer.setBackgroundColor(bg === "white" ? 0xFFFFFF : 0x020617);

        // ── Camera ────────────────────────────────────────────────────────────
        } else if (line === "zoom" || line === "zoom all" || line === "reset") {
            glViewer.zoomTo();

        } else if (line.startsWith("turn ") || line.startsWith("rotate ")) {
            // "turn y, 90" → rotate around Y axis 90°
            const m = line.match(/turn\s+([xyz]),\s*([\d.-]+)/);
            if (m) {
                const axis = m[1];
                const deg  = parseFloat(m[2]);
                if (axis === "x") glViewer.rotate(deg, { x: 1, y: 0, z: 0 });
                else if (axis === "y") glViewer.rotate(deg, { x: 0, y: 1, z: 0 });
                else if (axis === "z") glViewer.rotate(deg, { x: 0, y: 0, z: 1 });
            }
        }
        // Unrecognised lines are silently skipped
    }

    glViewer.render();
    console.log("3Dmol.js updated from PyMOL commands:", commandText);
}

// Apply full analysis API response to the UI
// Called after /api/analyze_smiles or external SMILES submission
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
    // Always refresh the ADME panel after any analysis response so it stays in sync
    // Use a small delay to allow canvas data to settle first
    if (data.ok !== false) {
        setTimeout(runADMEEvaluation, 100);
    }
}

// 3D Visualizer Globals and render3DModel function using 3Dmol.js
let glViewer = null;

function render3DModel(sdfData) {
    const container = document.getElementById("kinetic-3d-viewer");
    if (!container) {
        console.warn("render3DModel: #kinetic-3d-viewer container not found.");
        return;
    }
    
    // Clear container and make sure 3Dmol is loaded
    container.innerHTML = "";
    if (typeof $3Dmol === "undefined") {
        console.error("3Dmol.js is not loaded.");
        container.innerHTML = "<div style='color: #F87171; padding: 1.5rem; text-align: center; font-size: 0.8rem;'>Error: 3Dmol.js library not loaded.</div>";
        return;
    }
    
    try {
        glViewer = $3Dmol.createViewer(container, {
            backgroundColor: "#020617" // matches Tailwind bg-slate-950
        });
        
        glViewer.addModel(sdfData, "sdf");
        
        // Apply a premium, high-fidelity style: sticks for bonds, spheres for atoms
        glViewer.setStyle({}, {
            stick: {
                colorscheme: "Jmol",
                radius: 0.16
            },
            sphere: {
                colorscheme: "Jmol",
                scale: 0.28
            }
        });
        
        glViewer.zoomTo();
        glViewer.render();
        console.log("3D molecular conformer successfully rendered.");
    } catch (err) {
        console.error("Error rendering 3D model with 3Dmol.js:", err);
        container.innerHTML = `<div style='color: #F87171; padding: 1.5rem; text-align: center; font-size: 0.8rem;'>Error initializing 3D viewer: ${err.message}</div>`;
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
    // Original 6
    'C':  '#6B7280',
    'O':  '#DC2626',
    'N':  '#2563EB',
    'H':  '#9CA3AF',
    'P':  '#EA580C',
    'S':  '#CA8A04',
    // Halogens (drug design essentials)
    'F':  '#16A34A',   // green
    'Cl': '#15803D',   // dark green
    'Br': '#92400E',   // brown
    'I':  '#6D28D9',   // purple
    // Special atoms
    'B':  '#BE185D',   // pink (boronic acids)
    'Si': '#0E7490',   // teal (silicon bioisosteres)
    // New requested elements
    'Se': '#FF7F50',   // coral
    'Zn': '#7F8C8D',   // zinc grey
    'Fe': '#D2691E',   // chocolate/rust
    'Mg': '#20B2AA',   // light sea green
    'Na': '#9370DB',   // medium purple
    'K':  '#BA55D3',   // medium orchid
    'Pt': '#AFEEEE',   // pale turquoise
    'Au': '#FFD700',   // gold
    'Li': '#FF69B4',   // hot pink
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
    logAction("clear_canvas", {});
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
                    const oldType = clickedBond.type;
                    cycleBondType(clickedBond);
                    logAction("change_bond_type", { source_id: clickedBond.source, target_id: clickedBond.target, old_type: oldType, new_type: clickedBond.type });
                    saveSnapshot();
                    redraw();
                    pushPayload();
                    return;
                }
                const snap = snapGrid;
                const newX = Math.round(x / snap) * snap;
                const newY = Math.round(y / snap) * snap;
                const newAtomId = nextAtomId++;
                atoms.push({ id: newAtomId, x: newX, y: newY, element: activeElement });
                logAction("add_atom", { element: activeElement, x: newX, y: newY, atom_id: newAtomId });
                saveSnapshot();
                redraw(); pushPayload();
            }
        } else if (activeMode === "move") {
            if (clickedAtom) { 
                selectedAtom = clickedAtom; 
                isDragging = true; 
                window._dragStartCoords = { x: clickedAtom.x, y: clickedAtom.y }; 
            }
            else { isPanning = true; panStartX = sx - panX; panStartY = sy - panY; }
        } else if (activeMode === "erase") {
            if (clickedAtom) {
                atoms = atoms.filter(a => a.id !== clickedAtom.id);
                bonds = bonds.filter(b => b.source !== clickedAtom.id && b.target !== clickedAtom.id);
                logAction("delete_atom", { atom_id: clickedAtom.id });
                saveSnapshot();
                redraw(); pushPayload();
            } else {
                const oldBondCount = bonds.length;
                bonds = bonds.filter(bond => {
                    const a1 = atoms.find(a => a.id === bond.source);
                    const a2 = atoms.find(a => a.id === bond.target);
                    if (!a1 || !a2) return true;
                    if (distToSegment({x, y}, a1, a2) <= 8) {
                        logAction("delete_bond", { source_id: bond.source, target_id: bond.target });
                        return false;
                    }
                    return true;
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
                        const oldType = existingBond.type;
                        existingBond.type = activeBondType;
                        logAction("change_bond_type", { source_id: existingBond.source, target_id: existingBond.target, old_type: oldType, new_type: activeBondType });
                        changed = true;
                    }
                } else {
                    bonds.push({ source: dragStartAtom.id, target: targetAtom.id, type: activeBondType });
                    logAction("add_bond", { source_id: dragStartAtom.id, target_id: targetAtom.id, bond_type: activeBondType });
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
            if (window._dragStartCoords && (window._dragStartCoords.x !== selectedAtom.x || window._dragStartCoords.y !== selectedAtom.y)) {
                logAction("move_atom", { atom_id: selectedAtom.id, old_x: window._dragStartCoords.x, old_y: window._dragStartCoords.y, new_x: selectedAtom.x, new_y: selectedAtom.y });
            }
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

// PUSH payload - stores locally and triggers live ADME + 3D sync
function pushPayload() {
    const payload = {
        atoms: atoms.map(a => ({ id: a.id, x: a.x, y: a.y, element: a.element })),
        bonds: bonds.map(b => ({ source: b.source, target: b.target, type: b.type }))
    };
    lastSentPayload = JSON.stringify(payload);
    triggerDebouncedADME();      // Live ADME update (800ms debounce)
    triggerDebounced3DSync();    // Live 3D viewer sync (1200ms debounce)
}

// Fit all atoms into view with nice padding
function fitToView() {
    // If the 3D tab is active and the viewer is initialised, zoom the 3D model
    const is3DActive = document.getElementById('interactionViewContainer') &&
                       document.getElementById('interactionViewContainer').style.display !== 'none';
    if (is3DActive && glViewer) {
        glViewer.zoomTo();
        glViewer.render();
        return;
    }

    // Otherwise fit the 2D canvas
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
    console.log('Canvas loaded from RDKit backend:', atoms.length, 'atoms,', bonds.length, 'bonds');
    triggerDebouncedADME();      // Evaluate ADME for the loaded structure
    triggerDebounced3DSync();    // Sync 3D viewer for the loaded structure
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
        logAction("undo", {});
        redraw();
        pushPayload();
    }
}

function redo() {
    if (historyIndex < historyStack.length - 1) {
        historyIndex++;
        restoreSnapshot(historyStack[historyIndex]);
        logAction("redo", {});
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
    // ── 6-membered carbocyclics ────────────────────────────────────────────
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

    // ── 5-membered carbocyclic ─────────────────────────────────────────────
    cyclopentane: {
        atoms: 5, elements: ['C','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,0,1]],
        radius: 35
    },

    // ── 6-membered N-heterocyclics ─────────────────────────────────────────
    pyridine: {
        atoms: 6, elements: ['N','C','C','C','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,5,1],[5,0,2]],
        radius: 40
    },
    piperidine: {
        atoms: 6, elements: ['N','C','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]],
        radius: 40
    },
    morpholine: {
        atoms: 6, elements: ['N','C','C','O','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]],
        radius: 40
    },
    pyrimidine: {
        atoms: 6, elements: ['N','C','N','C','C','C'],
        bonds: [[0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,5,2],[5,0,1]],
        radius: 40
    },
    piperazine: {
        atoms: 6, elements: ['N','C','C','N','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]],
        radius: 40
    },
    dioxane: {
        atoms: 6, elements: ['O','C','C','O','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]],
        radius: 40
    },

    // ── 5-membered heterocyclics (aromatic & saturated) ───────────────────
    imidazole: {
        atoms: 5, elements: ['N','C','N','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    thiophene: {
        atoms: 5, elements: ['S','C','C','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    furan: {
        atoms: 5, elements: ['O','C','C','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    pyrrole: {
        atoms: 5, elements: ['N','C','C','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    pyrrolidine: {
        atoms: 5, elements: ['N','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,0,1]],
        radius: 35
    },
    tetrahydrofuran: {
        atoms: 5, elements: ['O','C','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,0,1]],
        radius: 35
    },
    thiazole: {
        atoms: 5, elements: ['S','C','N','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    oxazole: {
        atoms: 5, elements: ['O','C','N','C','C'],
        bonds: [[0,1,1],[1,2,2],[2,3,1],[3,4,2],[4,0,1]],
        radius: 35
    },
    pyrazole: {
        atoms: 5, elements: ['N','N','C','C','C'],
        bonds: [[0,1,1],[1,2,1],[2,3,2],[3,4,1],[4,0,2]],
        radius: 35
    },

    // ── Fused bicyclics ────────────────────────────────────────────────────
    naphthalene: {
        atoms: 10,
        elements: ['C','C','C','C','C','C','C','C','C','C'],
        bonds: [
            [0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,9,1],[9,0,2],  // ring 1
            [4,5,2],[5,6,1],[6,7,2],[7,8,1],[8,9,2]            // ring 2
        ],
        customPositions: [
            [-30, -52], [-60, -35], [-60, 35], [-30, 52], [0, 35], [30, 52], [60, 35], [60, -35], [30, -52], [0, -35]
        ],
        radius: 40
    },
    indole: {
        atoms: 9,
        elements: ['C','C','C','C','C','C','N','C','C'],
        bonds: [
            [0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,5,2],[5,0,1],  // benzene
            [4,6,1],[6,7,1],[7,8,2],[8,5,1]                    // pyrrole shared 4-5
        ],
        customPositions: [
            [-30, -52], [-60, -35], [-60, 35], [-30, 52], [0, 35], [0, -35],
            [35, 25], [45, -10], [30, -40]
        ],
        radius: 40
    },
    quinoline: {
        atoms: 10,
        elements: ['C','C','C','C','N','C','C','C','C','C'],
        bonds: [
            [0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,9,1],[9,0,2],
            [4,5,2],[5,6,1],[6,7,2],[7,8,1],[8,9,2]
        ],
        customPositions: [
            [-30, -52], [-60, -35], [-60, 35], [-30, 52], [0, 35], [30, 52], [60, 35], [60, -35], [30, -52], [0, -35]
        ],
        radius: 40
    },
    isoquinoline: {
        atoms: 10,
        elements: ['C','C','C','C','C','N','C','C','C','C'],
        bonds: [
            [0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,9,1],[9,0,2],
            [4,5,2],[5,6,1],[6,7,2],[7,8,1],[8,9,2]
        ],
        customPositions: [
            [-30, -52], [-60, -35], [-60, 35], [-30, 52], [0, 35], [30, 52], [60, 35], [60, -35], [30, -52], [0, -35]
        ],
        radius: 40
    },
    purine: {
        atoms: 9,
        elements: ['N','C','N','C','C','N','C','N','C'],
        bonds: [
            [0,1,2],[1,2,1],[2,3,2],[3,4,1],[4,5,2],[5,0,1],
            [4,6,1],[6,7,1],[7,8,2],[8,5,1]
        ],
        customPositions: [
            [-30, -52], [-60, -35], [-60, 35], [-30, 52], [0, 35], [0, -35],
            [35, 25], [45, -10], [30, -40]
        ],
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
        let x, y;
        if (tmpl.customPositions && tmpl.customPositions[i]) {
            // Bicyclic / fused templates define positions as [dx, dy] offsets from centre
            x = Math.round((centerX + tmpl.customPositions[i][0]) / 5) * 5;
            y = Math.round((centerY + tmpl.customPositions[i][1]) / 5) * 5;
        } else {
            const angle = i * angleStep - Math.PI / 2;
            x = Math.round((centerX + Math.cos(angle) * tmpl.radius) / 5) * 5;
            y = Math.round((centerY + Math.sin(angle) * tmpl.radius) / 5) * 5;
        }
        const id = nextAtomId++;
        idMap[i] = id;
        atoms.push({ id, x, y, element: elem });
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

// ==========================================
// Live 2D → 3D Sync (auto-render on draw)
// ==========================================
let sync3DTimeout = null;

function triggerDebounced3DSync() {
    if (sync3DTimeout) clearTimeout(sync3DTimeout);
    sync3DTimeout = setTimeout(runLive3DSync, 1200);
}

async function runLive3DSync() {
    if (atoms.length < 2) return; // Need at least a bond to make a valid 3D structure

    const smiles = await getActiveSmiles();
    if (!smiles) return;
    
    // Update design score
    updateDesignScore(smiles);

    try {
        const response = await fetch('/api/analyze_smiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ smiles })
        });
        const data = await response.json();
        if (!data.ok) return;

        // Update predictions and repurposing panels silently
        if (typeof data.predictions_html === 'string') {
            document.getElementById('dynamicPredictions').innerHTML = data.predictions_html;
        }
        if (typeof data.repurposing_html === 'string') {
            document.getElementById('dynamicRepurposing').innerHTML = data.repurposing_html;
        }

        // Fetch freshly-written SDF (cache-busted) and re-render 3D viewer
        const sdfRes = await fetch('/static/molecule.sdf?t=' + Date.now());
        const sdfData = await sdfRes.text();
        render3DModel(sdfData);

    } catch (e) {
        // Silent fail — 3D sync is best-effort, don't spam the user
        console.warn('Live 3D sync skipped:', e.message);
    }
}

async function getActiveSmiles() {
    // Read from the unified smart input field (replaces old Taipy-era visible_smiles_input)
    const unifiedInput = document.getElementById("unified_input");
    const inputVal = unifiedInput ? unifiedInput.value.trim() : "";
    // Only use it if it looks like a SMILES string (not a drug name)
    if (inputVal && /^[A-Za-z0-9@+\-\[\]()=#$:\/\\%.]+$/.test(inputVal) && /[=#\[\]@+\\\/]|[0-9]{1,2}/.test(inputVal)) {
        return inputVal;
    }
    
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

    const getProgressColorClass = (pass, borderline) => {
        if (pass) return "bg-emerald-500";
        if (borderline) return "bg-amber-500";
        return "bg-rose-500";
    };

    const getStatusIconHtml = (pass, borderline) => {
        if (pass) {
            return `<div class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><i class="fa-solid fa-check text-[10px]"></i></div>`;
        }
        if (borderline) {
            return `<div class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600"><i class="fa-solid fa-exclamation text-[10px]"></i></div>`;
        }
        return `<div class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-50 text-rose-600"><i class="fa-solid fa-xmark text-[10px]"></i></div>`;
    };

    const mwPercent = Math.min(100, (data.mw / 600) * 100);
    const mwColor = getProgressColorClass(data.mw_pass, data.mw > 450 && data.mw <= 500);
    const mwStatusIcon = getStatusIconHtml(data.mw_pass, data.mw > 450 && data.mw <= 500);

    const logPPercent = Math.min(100, Math.max(0, ((data.logp + 3) / 10) * 100));
    const logPColor = getProgressColorClass(data.logp_pass, data.logp > 4 && data.logp <= 5);
    const logPStatusIcon = getStatusIconHtml(data.logp_pass, data.logp > 4 && data.logp <= 5);

    const hbdPercent = Math.min(100, (data.hbd / 8) * 100);
    const hbdColor = getProgressColorClass(data.hbd_pass, data.hbd === 5);
    const hbdStatusIcon = getStatusIconHtml(data.hbd_pass, data.hbd === 5);

    const hbaPercent = Math.min(100, (data.hba / 15) * 100);
    const hbaColor = getProgressColorClass(data.hba_pass, data.hba === 10);
    const hbaStatusIcon = getStatusIconHtml(data.hba_pass, data.hba === 10);

    const tpsaPercent = Math.min(100, (data.tpsa / 180) * 100);
    const tpsaColor = getProgressColorClass(data.tpsa_pass, data.tpsa > 120 && data.tpsa <= 140);
    const tpsaStatusIcon = getStatusIconHtml(data.tpsa_pass, data.tpsa > 120 && data.tpsa <= 140);

    const rbPercent = Math.min(100, (data.rotatable_bonds / 15) * 100);
    const rbColor = getProgressColorClass(data.rb_pass, data.rotatable_bonds === 10);
    const rbStatusIcon = getStatusIconHtml(data.rb_pass, data.rotatable_bonds === 10);

    admeDiv.innerHTML = `
        <div class="flex flex-col gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200 mb-1">
            <div class="flex justify-between items-center text-xs">
                <span class="font-medium text-slate-500">Lipinski Rule of 5</span>
                <span class="inline-flex items-center gap-1 font-semibold ${data.lipinski_pass ? 'text-emerald-600' : 'text-rose-600'}">
                    <i class="${data.lipinski_pass ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-xmark'}"></i>
                    ${data.lipinski_pass ? 'Pass' : `Fail (${data.lipinski_violations})`}
                </span>
            </div>
            <div class="h-px bg-slate-200 w-full"></div>
            <div class="flex justify-between items-center text-xs">
                <span class="font-medium text-slate-500">Veber Filter</span>
                <span class="inline-flex items-center gap-1 font-semibold ${data.veber_pass ? 'text-emerald-600' : 'text-rose-600'}">
                    <i class="${data.veber_pass ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-xmark'}"></i>
                    ${data.veber_pass ? 'Pass' : 'Fail'}
                </span>
            </div>
        </div>

        <div class="grid grid-cols-3 gap-2 text-[11px] text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-200 mb-1">
            <div class="truncate">Formula: <strong class="font-mono text-slate-900">${data.molecular_formula}</strong></div>
            <div class="text-center truncate">Heavy Atoms: <strong class="text-slate-900">${data.heavy_atom_count}</strong></div>
            <div class="text-right truncate">Rings: <strong class="text-slate-900">${data.ring_count}</strong></div>
        </div>

        <div class="flex flex-col gap-3">
            <!-- Molecular Weight -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">Mol. Weight</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.mw}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${mwColor}" style="width: ${mwPercent}%"></div>
                </div>
                ${mwStatusIcon}
            </div>

            <!-- LogP -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">LogP</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.logp}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${logPColor}" style="width: ${logPPercent}%"></div>
                </div>
                ${logPStatusIcon}
            </div>

            <!-- H-Bond Donors -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">H-Bond Donors</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.hbd}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${hbdColor}" style="width: ${hbdPercent}%"></div>
                </div>
                ${hbdStatusIcon}
            </div>

            <!-- H-Bond Acceptors -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">H-Bond Acceptors</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.hba}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${hbaColor}" style="width: ${hbaPercent}%"></div>
                </div>
                ${hbaStatusIcon}
            </div>

            <!-- TPSA -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">Polar Surf. Area</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.tpsa}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${tpsaColor}" style="width: ${tpsaPercent}%"></div>
                </div>
                ${tpsaStatusIcon}
            </div>

            <!-- Rotatable Bonds -->
            <div class="grid grid-cols-[minmax(88px,1fr)_56px_1fr_20px] items-center gap-2.5">
                <div class="truncate text-xs font-medium leading-4 text-slate-700">Rotatable Bonds</div>
                <div class="text-right font-mono text-[11px] tabular-nums text-slate-900 leading-4 whitespace-nowrap">${data.rotatable_bonds}</div>
                <div class="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="absolute left-0 top-0 h-full rounded-full ${rbColor}" style="width: ${rbPercent}%"></div>
                </div>
                ${rbStatusIcon}
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

async function runOneClickDocking() {
    const pdbIdInput = document.getElementById("pdbIdInput");
    const pdbId = pdbIdInput ? pdbIdInput.value.trim().toUpperCase() : "";
    if (!pdbId || pdbId.length !== 4) {
        alert("Please enter and fetch a valid PDB ID first.");
        return;
    }
    
    // Get current ligand selection for autobox
    const ligandSelect = document.getElementById("ligandSelect");
    const ligandResname = ligandSelect ? ligandSelect.value : "";
    
    const btn = document.getElementById("btnDockGnina");
    if (btn) { btn.disabled = true; btn.textContent = "Docking..."; }
    
    try {
        const response = await fetch("/api/dock", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                pdb_id: pdbId,
                ligand_resname: ligandResname,
                ligand_sdf_path: "molecule.sdf"
            })
        });
        const data = await response.json();
        
        if (data.ok && data.poses && data.poses.length > 0) {
            let resultHtml = "<div style='padding:8px;'><strong>GNINA Docking Results</strong><br>";
            data.poses.forEach(pose => {
                resultHtml += `<div>Mode ${pose.mode}: ΔG = ${pose.affinity_kcal.toFixed(2)} kcal/mol`;
                if (pose.cnn_score) resultHtml += ` | CNN: ${pose.cnn_score.toFixed(3)}`;
                resultHtml += `</div>`;
            });
            resultHtml += "</div>";
            
            const logBox = document.getElementById("dynamicCheckpointLogs");
            if (logBox) logBox.innerHTML += resultHtml;
            
            // Load best docked pose into 3D viewer
            if (data.output_sdf) {
                const sdfRes = await fetch(`/static/${data.output_sdf}`);
                const sdfText = await sdfRes.text();
                render3DModel(sdfText);
            }
        } else {
            alert(data.error || "Docking returned no poses.");
        }
    } catch (e) {
        alert("Docking failed: " + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "⚡ Dock with GNINA"; }
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
        
        // Resize 3Dmol viewer to fit the visible container size correctly
        if (glViewer) {
            glViewer.resize();
            glViewer.render();
        }
    }
}

// ==========================================
// PubChem API Compound Resolver & Search
// ==========================================
async function triggerPubChemSearch() {
    const searchVal = document.getElementById("pubchem_search_input").value.trim();
    if (!searchVal) return;
    
    const btn = document.querySelector(".smiles-bar button[onclick='triggerPubChemSearch()']");
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Searching...";
    
    const logBox = document.getElementById("dynamicCheckpointLogs");
    if (logBox) {
        logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[PUBCHEM]</span> Querying PubChem database for '${searchVal}'...</div>`;
    }
    
    try {
        const res = await fetch(`/api/pubchem/fetch?name=${encodeURIComponent(searchVal)}`);
        const data = await res.json();
        if (data.ok && data.smiles) {
            document.getElementById("visible_smiles_input").value = data.smiles;
            if (logBox) {
                logBox.innerHTML += `<div class="checkpoint-log-line"><span class="checkpoint-time">[PUBCHEM]</span> Found SMILES: ${data.smiles}</div>`;
                document.getElementById("checkpointBody").scrollTop = 99999;
            }
            // Automatically analyze and render the resolved compound
            triggerSmilesPasted();
        } else {
            alert("PubChem: " + (data.error || "Compound not found."));
        }
    } catch (e) {
        console.error("PubChem search error:", e);
        alert("PubChem search failed.");
    } finally {
        btn.disabled = false;
        btn.textContent = origText;
    }
}

// ==========================================
// 3D Conformer File Downloader Utility
// ==========================================
function downloadStructure(format) {
    const url = `/static/molecule.${format}`;
    const link = document.createElement("a");
    link.href = url;
    link.download = `kinetic_sketch_conformer.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    console.log(`Downloading optimized 3D coordinate conformer in .${format} format.`);
}

// ==========================================
// 3D Visualizer Style Toggles (3Dmol.js)
// ==========================================
function toggle3DStyle(styleType) {
    if (!glViewer) {
        console.warn("toggle3DStyle: 3D viewer is not initialized.");
        return;
    }
    
    glViewer.removeAllStyles();
    
    if (styleType === 'stick') {
        glViewer.setStyle({}, { stick: { colorscheme: 'Jmol', radius: 0.16 }, sphere: { colorscheme: 'Jmol', scale: 0.28 } });
    } else if (styleType === 'sphere') {
        glViewer.setStyle({}, { sphere: { colorscheme: 'Jmol', scale: 0.8 } });
    } else if (styleType === 'line') {
        glViewer.setStyle({}, { line: { colorscheme: 'Jmol', linewidth: 1.5 } });
    } else if (styleType === 'cartoon') {
        glViewer.setStyle({}, { cartoon: { colorscheme: 'Jmol' }, stick: { colorscheme: 'Jmol', radius: 0.1 } });
    }
    
    glViewer.render();
    console.log(`Changed 3Dmol style to: ${styleType}`);
}

// ── Design Score Widget ────────────────────────────────────────────
async function updateDesignScore(smiles) {
    if (!smiles) return;
    try {
        const res = await fetch("/api/design_score", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ smiles })
        });
        const data = await res.json();
        const scoreWidget = document.getElementById("designScoreWidget");
        if (scoreWidget && data.ok) {
            scoreWidget.innerHTML = `
                <div style="display:flex; align-items:center; gap:8px; padding:6px 12px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px;">
                    <div style="width:40px; height:40px; border-radius:50%; background:${data.color}; display:flex; align-items:center; justify-content:center; color:white; font-weight:700; font-size:14px;">
                        ${data.grade}
                    </div>
                    <div>
                        <div style="font-size:18px; font-weight:700; color:${data.color};">${data.score}</div>
                        <div style="font-size:10px; color:#64748B;">Design Score</div>
                    </div>
                </div>
            `;
        }
    } catch (e) { /* silent */ }
}