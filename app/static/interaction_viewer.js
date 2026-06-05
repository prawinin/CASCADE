// app/static/interaction_viewer.js
// Standalone SVG Interaction Diagram Renderer for KineticSketch

function renderInteractionDiagram(interactions, ligand2d) {
    const container = document.getElementById("interactionDiagramContainer");
    if (!container) return;

    if (!interactions || !ligand2d || ligand2d.atoms.length === 0) {
        container.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-tertiary); padding:2rem; text-align:center;">
                <i class="fa-solid fa-circle-nodes" style="font-size:32px; margin-bottom:1rem; opacity:0.5;"></i>
                <div style="font-weight:600; margin-bottom:0.25rem;">No Interaction Profile Loaded</div>
                <div style="font-size:0.75rem; max-width:260px;">Select a PDB target and ligand residue in the right sidebar to compute physics-based binding interactions.</div>
            </div>
        `;
        return;
    }

    const svgWidth = 550;
    const svgHeight = 550;
    const center = { x: svgWidth / 2, y: svgHeight / 2 };

    // 1. Center and scale ligand coordinates
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    ligand2d.atoms.forEach(a => {
        if (a.x < minX) minX = a.x;
        if (a.x > maxX) maxX = a.x;
        if (a.y < minY) minY = a.y;
        if (a.y > maxY) maxY = a.y;
    });

    const ligW = maxX - minX || 1;
    const ligH = maxY - minY || 1;
    
    // Fit ligand inside a 180x180 box in the center
    const targetBoxSize = 180;
    const scale = Math.min(targetBoxSize / ligW, targetBoxSize / ligH);
    const ligCX = (minX + maxX) / 2;
    const ligCY = (minY + maxY) / 2;

    const getScaledCoords = (x, y) => {
        return {
            x: center.x + (x - ligCX) * scale,
            y: center.y - (y - ligCY) * scale // Flip Y coordinates to match standard molecular layout
        };
    };

    // Store mapped coordinates of ligand atoms
    const atomCoords = {};
    ligand2d.atoms.forEach(atom => {
        atomCoords[atom.id] = getScaledCoords(atom.x, atom.y);
    });

    // 2. Identify all unique residues involved in interactions
    const residuesMap = {};
    interactions.forEach(inter => {
        const res = inter.residue;
        const resId = `${res.name}_${res.chain}_${res.seq}`;
        if (!residuesMap[resId]) {
            residuesMap[resId] = {
                name: res.name,
                chain: res.chain,
                seq: res.seq,
                interactions: [],
                connectedAtomIds: new Set()
            };
        }
        residuesMap[resId].interactions.push(inter);
        
        // Find corresponding ligand atom by name (e.g. C12 or N2)
        const lAtomName = inter.ligand_atom.name;
        // In our coordinates, atom IDs are 1-based index, but name might be C1, N2 etc.
        // We find the closest element/number or match by atom name
        // Wait, backend matches them by PDB atom names. Let's match by index if possible,
        // otherwise let's just find the closest atom in the ligand 2D set by symbol
        let matchedAtomId = null;
        const symbol = inter.ligand_atom.element;
        
        // Match by element and count-based heuristic, or simply exact name match
        // Let's search ligand2d.atoms for atom that matches the element symbol
        const candidates = ligand2d.atoms.filter(a => a.element === symbol);
        if (candidates.length > 0) {
            // Find closest candidate index based on atom name if it contains numbers
            const numPart = parseInt(lAtomName.replace(/\D/g, ''));
            if (!isNaN(numPart) && numPart <= candidates.length) {
                matchedAtomId = candidates[numPart - 1].id;
            } else {
                matchedAtomId = candidates[0].id;
            }
        }
        
        if (matchedAtomId) {
            residuesMap[resId].connectedAtomIds.add(matchedAtomId);
            inter.matchedAtomId = matchedAtomId;
        }
    });

    const residues = Object.values(residuesMap);

    // 3. Radial positioning of residues based on the centroid of their connected ligand atoms
    residues.forEach(res => {
        // Calculate average angle of connected ligand atoms from center
        let sumX = 0, sumY = 0;
        res.connectedAtomIds.forEach(id => {
            if (atomCoords[id]) {
                sumX += atomCoords[id].x - center.x;
                sumY += atomCoords[id].y - center.y;
            }
        });
        
        let angle = Math.atan2(sumY, sumX);
        if (res.connectedAtomIds.size === 0) {
            angle = Math.random() * 2 * Math.PI;
        }
        res.angle = angle;
    });

    // Sort residues by angle to prevent crossing lines
    residues.sort((a, b) => a.angle - b.angle);

    // Position residues uniformly in a circle with radius 210px
    const radialRadius = 210;
    residues.forEach((res, i) => {
        const theta = (i / residues.length) * 2 * Math.PI - Math.PI / 2; // start from 12 o'clock
        res.x = center.x + Math.cos(theta) * radialRadius;
        res.y = center.y + Math.sin(theta) * radialRadius;
    });

    // 4. Render SVG
    let svgContent = `<svg width="100%" height="100%" viewBox="0 0 ${svgWidth} ${svgHeight}" xmlns="http://www.w3.org/2000/svg" style="background:#FFFFFF; font-family:'Inter', sans-serif;">`;
    
    // Define markers, filters, or gradients if needed
    svgContent += `
        <defs>
            <filter id="badgeShadow" x="-10%" y="-10%" width="120%" height="120%">
                <feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-opacity="0.08" />
            </filter>
        </defs>
    `;

    // A. Draw interaction lines (underneath atoms/residues)
    interactions.forEach(inter => {
        const resId = `${inter.residue.name}_${inter.residue.chain}_${inter.residue.seq}`;
        const res = residuesMap[resId];
        const latomCoord = inter.matchedAtomId ? atomCoords[inter.matchedAtomId] : center;
        
        if (!res || !latomCoord) return;

        // Interaction styles
        let strokeColor = "#9CA3AF";
        let dashArray = "4,4";
        let labelColor = "#4B5563";
        let typeLabel = "";

        switch (inter.type) {
            case "hydrogen_bond":
                strokeColor = "#2563EB"; // Blue
                dashArray = "5,4";
                labelColor = "#1D4ED8";
                typeLabel = "H-bond";
                break;
            case "halogen_bond":
                strokeColor = "#059669"; // Green
                dashArray = "5,4";
                labelColor = "#047857";
                typeLabel = "Halogen";
                break;
            case "salt_bridge":
                strokeColor = "#DC2626"; // Red
                dashArray = "6,3";
                labelColor = "#B91C1C";
                typeLabel = "Salt Bridge";
                break;
            case "pi_stacking_parallel":
                strokeColor = "#7C3AED"; // Purple
                dashArray = "1,0"; // solid line for aromatic interaction
                labelColor = "#5B21B6";
                typeLabel = "π-π parallel";
                break;
            case "pi_stacking_t_shaped":
                strokeColor = "#8B5CF6";
                dashArray = "4,4";
                labelColor = "#6D28D9";
                typeLabel = "π-π T-shape";
                break;
            case "pi_cation":
                strokeColor = "#D97706"; // Amber
                dashArray = "5,3";
                labelColor = "#B45309";
                typeLabel = "π-Cation";
                break;
            case "hydrophobic_contact":
                strokeColor = "#9CA3AF"; // Gray dots
                dashArray = "2,3";
                labelColor = "#4B5563";
                typeLabel = "Hydrophobic";
                break;
        }

        // Draw line
        svgContent += `
            <line x1="${latomCoord.x}" y1="${latomCoord.y}" x2="${res.x}" y2="${res.y}" 
                  stroke="${strokeColor}" stroke-width="2" stroke-dasharray="${dashArray}" opacity="0.85" />
        `;

        // Draw distance tag at midpoint
        const midX = (latomCoord.x + res.x) / 2;
        const midY = (latomCoord.y + res.y) / 2;
        
        svgContent += `
            <g transform="translate(${midX}, ${midY})">
                <rect x="-24" y="-8" width="48" height="15" rx="3" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="0.5" />
                <text x="0" y="2" font-size="8px" font-weight="600" fill="${labelColor}" text-anchor="middle">
                    ${inter.distance_angstrom}Å
                </text>
            </g>
        `;
    });

    // B. Draw Ligand Bonds
    ligand2d.bonds.forEach(bond => {
        const a1 = atomCoords[bond.source];
        const a2 = atomCoords[bond.target];
        if (!a1 || !a2) return;

        const angle = Math.atan2(a2.y - a1.y, a2.x - a1.x);
        const offset_x = Math.sin(angle) * 2;
        const offset_y = Math.cos(angle) * 2;

        if (bond.type === 1) {
            svgContent += `<line x1="${a1.x}" y1="${a1.y}" x2="${a2.x}" y2="${a2.y}" stroke="#1E293B" stroke-width="2" />`;
        } else if (bond.type === 2) {
            svgContent += `
                <line x1="${a1.x - offset_x}" y1="${a1.y + offset_y}" x2="${a2.x - offset_x}" y2="${a2.y + offset_y}" stroke="#1E293B" stroke-width="1.8" />
                <line x1="${a1.x + offset_x}" y1="${a1.y - offset_y}" x2="${a2.x + offset_x}" y2="${a2.y - offset_y}" stroke="#1E293B" stroke-width="1.8" />
            `;
        } else if (bond.type === 3) {
            svgContent += `
                <line x1="${a1.x}" y1="${a1.y}" x2="${a2.x}" y2="${a2.y}" stroke="#1E293B" stroke-width="1.5" />
                <line x1="${a1.x - offset_x*1.5}" y1="${a1.y + offset_y*1.5}" x2="${a2.x - offset_x*1.5}" y2="${a2.y + offset_y*1.5}" stroke="#1E293B" stroke-width="1.5" />
                <line x1="${a1.x + offset_x*1.5}" y1="${a1.y - offset_y*1.5}" x2="${a2.x + offset_x*1.5}" y2="${a2.y - offset_y*1.5}" stroke="#1E293B" stroke-width="1.5" />
            `;
        }
    });

    // C. Draw Ligand Atoms
    const elementColors = {
        'C': '#475569',
        'O': '#EF4444',
        'N': '#3B82F6',
        'H': '#94A3B8',
        'P': '#F97316',
        'S': '#EAB308'
    };

    ligand2d.atoms.forEach(atom => {
        const coord = atomCoords[atom.id];
        if (!coord) return;

        // Atom circle background to hide bond line overlap
        svgContent += `
            <circle cx="${coord.x}" cy="${coord.y}" r="11" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1" />
        `;

        // Atom Symbol text
        const color = elementColors[atom.element] || '#1E293B';
        svgContent += `
            <text x="${coord.x}" y="${coord.y + 0.5}" font-size="11px" font-weight="700" fill="${color}" 
                  text-anchor="middle" dominant-baseline="central">
                ${atom.element}
            </text>
        `;
    });

    // D. Draw Residue Nodes (Pills)
    // Custom coloring based on residue category
    const getResidueColorStyles = (name) => {
        name = name.toUpperCase();
        // Negative / Acidic: ASP, GLU
        if (["ASP", "GLU"].includes(name)) {
            return { bg: "#FEF2F2", border: "#FCA5A5", text: "#991B1B" };
        }
        // Positive / Basic: ARG, LYS, HIS
        if (["ARG", "LYS", "HIS"].includes(name)) {
            return { bg: "#EFF6FF", border: "#93C5FD", text: "#1E40AF" };
        }
        // Aromatic: PHE, TYR, TRP
        if (["PHE", "TYR", "TRP"].includes(name)) {
            return { bg: "#FAF5FF", border: "#D8B4FE", text: "#5B21B6" };
        }
        // Hydrophobic: ALA, VAL, LEU, ILE, PRO, MET
        if (["ALA", "VAL", "LEU", "ILE", "PRO", "MET"].includes(name)) {
            return { bg: "#F9FAFB", border: "#D1D5DB", text: "#374151" };
        }
        // Polar Neutral: SER, THR, ASN, GLN, CYS
        return { bg: "#ECFDF5", border: "#6EE7B7", text: "#065F46" };
    };

    residues.forEach(res => {
        const style = getResidueColorStyles(res.name);
        const label = `${res.name} ${res.chain}:${res.seq}`;
        
        // Calculate pill dimensions based on text length
        const charCount = label.length;
        const pillW = charCount * 6.8 + 14;
        const pillH = 22;

        svgContent += `
            <g transform="translate(${res.x}, ${res.y})" filter="url(#badgeShadow)">
                <rect x="${-pillW/2}" y="${-pillH/2}" width="${pillW}" height="${pillH}" rx="11" 
                      fill="${style.bg}" stroke="${style.border}" stroke-width="1.5" />
                <text x="0" y="1" font-size="10px" font-weight="700" fill="${style.text}" 
                      text-anchor="middle" dominant-baseline="middle">
                    ${label}
                </text>
            </g>
        `;
    });

    svgContent += "</svg>";
    container.innerHTML = svgContent;
}

// Download Interaction Diagram SVG function
function downloadInteractionSVG() {
    const container = document.getElementById("interactionDiagramContainer");
    if (!container) return;
    const svgEl = container.querySelector("svg");
    if (!svgEl) return;
    
    try {
        const svgData = new XMLSerializer().serializeToString(svgEl);
        const svgBlob = new Blob([svgData], {type: "image/svg+xml;charset=utf-8"});
        const svgUrl = URL.createObjectURL(svgBlob);
        const downloadLink = document.createElement("a");
        downloadLink.href = svgUrl;
        downloadLink.download = "kinetic_sketch_interaction_profile.svg";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
        console.log("Downloaded interaction diagram SVG successfully.");
    } catch (e) {
        console.error("Failed to download interaction SVG:", e);
    }
}
