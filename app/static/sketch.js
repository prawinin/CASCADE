
        // React Input Value Setter Utility
        function setReactInputValue(containerId, value) {
            const el = document.getElementById(containerId);
            if (!el) {
                console.warn("setReactInputValue: element not found:", containerId);
                return;
            }
            
            // If the element itself is input/textarea, use it. Otherwise search children.
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
                // For Taipy, it often listens to 'blur' or 'keyup' with Enter
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
                // If no SMILES input, check if we have drawn something on the canvas
                if (atoms.length === 0) {
                    const logBox = document.getElementById("dynamicCheckpointLogs");
                    if (logBox) {
                        logBox.innerHTML = `<div class="checkpoint-log-line"><span class="checkpoint-time">[WARNING]</span> Please draw a molecule or enter a SMILES string to analyze.</div>`;
                    }
                    return;
                }
                // If we have drawn molecules, we could trigger analysis via canvas payload,
                // but since canvas payload is already processed via Taipy reactivity,
                // we just notify the user that analysis is already in progress or completed.
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

            // Optimistically show the user's message
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
                drawGrid();
            }
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

        // Dragging & Interaction variables
        let selectedAtom = null;
        let hoveredAtom = null;
        let dragStartAtom = null;
        let isDragging = false;
        let dragX = 0;
        let dragY = 0;
        let snapGrid = 15;

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

        function resizeCanvas() {
            const container = document.getElementById("canvasContainer");
            if (!container || !canvas) return;
            canvas.width = container.clientWidth;
            canvas.height = container.clientHeight;
            redraw();
        }

        window.addEventListener('resize', resizeCanvas);

        function setMode(mode) {
            activeMode = mode;
            document.getElementById("btnDraw").classList.toggle("active", mode === "draw");
            document.getElementById("btnMove").classList.toggle("active", mode === "move");
            document.getElementById("btnErase").classList.toggle("active", mode === "erase");
        }

        function setActiveElement(el, btn) {
            activeElement = el;
            document.querySelectorAll(".left-rail .rail-btn").forEach(b => {
                if (b.innerText && (b.innerText.trim() === "C" || b.innerText.trim() === "N" || b.innerText.trim() === "O" || b.innerText.trim() === "H" || b.innerText.trim() === "P" || b.innerText.trim() === "S")) {
                    b.classList.remove("active-element");
                }
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

        // Draw coordinate grid (subtle, softer opacity)
        function drawGrid() {
            if (!ctx || !canvas) return;
            ctx.strokeStyle = "rgba(0, 0, 0, 0.04)";
            ctx.lineWidth = 1;
            const gridSz = 40;
            for (let x = 0; x < canvas.width; x += gridSz) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }
            for (let y = 0; y < canvas.height; y += gridSz) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }
        }

        // Main redraw function
        function redraw() {
            if (!ctx || !canvas) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            drawGrid();

            // 1. Draw Bonds
            bonds.forEach(bond => {
                const a1 = atoms.find(a => a.id === bond.source);
                const a2 = atoms.find(a => a.id === bond.target);
                if (!a1 || !a2) return;

                ctx.strokeStyle = "#94A3B8";
                ctx.lineWidth = 3;

                // Single, Double, Triple lines
                const angle = Math.atan2(a2.y - a1.y, a2.x - a1.x);
                const offset_x = Math.sin(angle) * 5;
                const offset_y = Math.cos(angle) * 5;

                if (bond.type === 1) {
                    ctx.beginPath();
                    ctx.moveTo(a1.x, a1.y);
                    ctx.lineTo(a2.x, a2.y);
                    ctx.stroke();
                } else if (bond.type === 2) {
                    ctx.beginPath();
                    ctx.moveTo(a1.x - offset_x, a1.y + offset_y);
                    ctx.lineTo(a2.x - offset_x, a2.y + offset_y);
                    ctx.moveTo(a1.x + offset_x, a1.y - offset_y);
                    ctx.lineTo(a2.x + offset_x, a2.y - offset_y);
                    ctx.stroke();
                } else if (bond.type === 3) {
                    ctx.beginPath();
                    ctx.moveTo(a1.x, a1.y);
                    ctx.lineTo(a2.x, a2.y);
                    ctx.moveTo(a1.x - offset_x * 1.5, a1.y + offset_y * 1.5);
                    ctx.lineTo(a2.x - offset_x * 1.5, a2.y + offset_y * 1.5);
                    ctx.moveTo(a1.x + offset_x * 1.5, a1.y - offset_y * 1.5);
                    ctx.lineTo(a2.x + offset_x * 1.5, a2.y - offset_y * 1.5);
                    ctx.stroke();
                }
            });

            // Draw active bond line while drawing
            if (activeMode === "draw" && isDragging && dragStartAtom) {
                ctx.strokeStyle = "rgba(37, 99, 235, 0.5)";
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 5]);
                ctx.beginPath();
                ctx.moveTo(dragStartAtom.x, dragStartAtom.y);
                ctx.lineTo(dragX, dragY);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // 2. Draw Atoms
            atoms.forEach(atom => {
                const color = elementColors[atom.element] || '#ffffff';
                const isHovered = hoveredAtom && hoveredAtom.id === atom.id;

                // Outer circle background
                ctx.fillStyle = "#FFFFFF";
                ctx.strokeStyle = isHovered ? "var(--accent-blue)" : "#D1D5DB";
                ctx.lineWidth = isHovered ? 2 : 1;
                ctx.beginPath();
                ctx.arc(atom.x, atom.y, atomRadius, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();

                // Hover glow
                if (isHovered) {
                    ctx.shadowColor = "rgba(37, 99, 235, 0.35)";
                    ctx.shadowBlur = 8;
                }

                // Element text
                ctx.fillStyle = color;
                ctx.font = "bold 13px 'Inter', sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(atom.element, atom.x, atom.y);

                // Clear shadow
                ctx.shadowBlur = 0;
            });
        }

        // Handle mouse canvas actions
        if (canvas) {
            canvas.addEventListener('mousedown', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const clickedAtom = getAtomAt(x, y);

                if (activeMode === "draw") {
                    if (clickedAtom) {
                        // Start drawing bond
                        dragStartAtom = clickedAtom;
                        isDragging = true;
                        dragX = x;
                        dragY = y;
                    } else {
                        // Create new atom
                        const newAtom = {
                            id: nextAtomId++,
                            x: Math.round(x / snapGrid) * snapGrid,
                            y: Math.round(y / snapGrid) * snapGrid,
                            element: activeElement
                        };
                        atoms.push(newAtom);
                        redraw();
                        pushPayload();
                    }
                } else if (activeMode === "move") {
                    if (clickedAtom) {
                        selectedAtom = clickedAtom;
                        isDragging = true;
                    }
                } else if (activeMode === "erase") {
                    if (clickedAtom) {
                        // Delete atom and connected bonds
                        atoms = atoms.filter(a => a.id !== clickedAtom.id);
                        bonds = bonds.filter(b => b.source !== clickedAtom.id && b.target !== clickedAtom.id);
                        redraw();
                        pushPayload();
                    } else {
                        // Check if clicked a bond
                        bonds = bonds.filter(bond => {
                            const a1 = atoms.find(a => a.id === bond.source);
                            const a2 = atoms.find(a => a.id === bond.target);
                            if (!a1 || !a2) return true;
                            
                            // Distance from point to line segment
                            const d = distToSegment({x, y}, a1, a2);
                            return d > 8; // If within 8px, delete it
                        });
                        redraw();
                        pushPayload();
                    }
                }
            });

            canvas.addEventListener('mousemove', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                const oldHover = hoveredAtom;
                hoveredAtom = getAtomAt(x, y);

                if (oldHover !== hoveredAtom) {
                    redraw();
                }

                if (isDragging) {
                    if (activeMode === "draw") {
                        dragX = x;
                        dragY = y;
                        redraw();
                    } else if (activeMode === "move" && selectedAtom) {
                        selectedAtom.x = Math.round(x / snapGrid) * snapGrid;
                        selectedAtom.y = Math.round(y / snapGrid) * snapGrid;
                        redraw();
                    }
                }
            });

            canvas.addEventListener('mouseup', (e) => {
                if (!isDragging) return;
                isDragging = false;

                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                if (activeMode === "draw" && dragStartAtom) {
                    const targetAtom = getAtomAt(x, y);
                    if (targetAtom && targetAtom.id !== dragStartAtom.id) {
                        // Check if bond already exists
                        const existingBond = bonds.find(b => 
                            (b.source === dragStartAtom.id && b.target === targetAtom.id) ||
                            (b.source === targetAtom.id && b.target === dragStartAtom.id)
                        );

                        if (existingBond) {
                            // Toggle bond type or update it
                            existingBond.type = activeBondType;
                        } else {
                            // Create a new bond
                            bonds.push({
                                source: dragStartAtom.id,
                                target: targetAtom.id,
                                type: activeBondType
                            });
                        }
                        pushPayload();
                    }
                    dragStartAtom = null;
                }

                if (activeMode === "move" && selectedAtom) {
                    selectedAtom = null;
                    pushPayload();
                }

                redraw();
            });
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

        // PUSH payload from Canvas to Taipy Backend
        function pushPayload() {
            const payload = {
                atoms: atoms.map(a => ({ id: a.id, x: a.x, y: a.y, element: a.element })),
                bonds: bonds.map(b => ({ source: b.source, target: b.target, type: b.type }))
            };
            const payloadStr = JSON.stringify(payload);
            lastSentPayload = payloadStr;
            setReactInputValue("taipy_canvas_payload", payloadStr);
            console.log("Drawn canvas payload pushed:", payloadStr);
        }

        // LOAD canvas data from Backend (e.g. from pasted SMILES)
        function loadCanvasData(data) {
            if (!data || !data.atoms) return;
            
            // Re-scale coordinates to fit canvas nicely
            atoms = [];
            bonds = [];
            
            if (data.atoms.length === 0) {
                redraw();
                return;
            }

            // Find bounds of loaded data
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            data.atoms.forEach(a => {
                if (a.x < minX) minX = a.x;
                if (a.x > maxX) maxX = a.x;
                if (a.y < minY) minY = a.y;
                if (a.y > maxY) maxY = a.y;
            });

            // Center of loaded structure
            const dataCenterX = (minX + maxX) / 2;
            const dataCenterY = (minY + maxY) / 2;

            // Center of canvas
            const canvasCenterX = canvas.width / 2;
            const canvasCenterY = canvas.height / 2;

            // Determine scaling factor
            let scale = 50; // default scaling factor for RDKit raw 2D coords
            if (maxX - minX > 0.1 || maxY - minY > 0.1) {
                const scaleX = (canvas.width - 200) / (maxX - minX);
                const scaleY = (canvas.height - 200) / (maxY - minY);
                scale = Math.min(scaleX, scaleY);
                // Limit scale to a reasonable size
                scale = Math.max(20, Math.min(scale, 100));
            }

            // Load atoms with scaled/centered coords
            data.atoms.forEach(a => {
                atoms.push({
                    id: a.id,
                    x: Math.round((canvasCenterX + (a.x - dataCenterX) * scale) / snapGrid) * snapGrid,
                    y: Math.round((canvasCenterY + (a.y - dataCenterY) * scale) / snapGrid) * snapGrid,
                    element: a.element
                });
            });

            // Load bonds
            if (data.bonds) {
                data.bonds.forEach(b => {
                    bonds.push({
                        source: b.source,
                        target: b.target,
                        type: b.type
                    });
                });
            }

            // Find highest atom ID to keep nextAtomId sequential
            nextAtomId = Math.max(...atoms.map(a => a.id), 0) + 1;

            redraw();
            console.log("Canvas loaded structures from RDKit backend!");
        }
    