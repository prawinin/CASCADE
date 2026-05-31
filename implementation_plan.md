# UI Overhaul — KineticSketch AI (World-Class Redesign)

Redesign `index.html` to match the quality of premium molecular workspace tools (MolView, Ketcher/EPAM, Molstar/RCSB PDB, Schrödinger LiveDesign) while keeping ALL existing Taipy bindings, JavaScript canvas engine, and Python backend integrations 100% intact.

## Inspiration Sources (Best Parts From Each)

| Source | What We Take |
|--------|-------------|
| **Ketcher (EPAM)** | Left vertical icon toolbar rail, clean tool segmentation, professional spacing |
| **Molstar (RCSB PDB)** | Minimal chrome philosophy, dark elevation hierarchy, data-first panels |
| **MolView** | Split-view architecture feel, real-time sync magic |
| **Modern Dashboard 2026** | Inter font, GitHub-style elevation layers, refined glassmorphism, micro-animations |

---

## Proposed Changes

### [MODIFY] [index.html](file:///home/prawin/Documents/GitHub/KineticSketch/index.html)

#### 1. Font System Change
- **Body/UI**: `Inter` (industry-standard for scientific UIs — tall x-height, exceptional small-size readability) with tabular figures (`font-feature-settings: 'tnum' 1`)
- **Code/Data**: `JetBrains Mono` (keep)
- **Logo**: Inter Display 800 with gradient (replacing Outfit)

#### 2. Color System Upgrade — GitHub-Style Elevation Layers

```
Surface 0 (body):     #0D1117  (deep charcoal, NOT pure black)
Surface 1 (panels):   #161B22  (cards, sidebars)
Surface 2 (hover):    #21262D  (active states, elevated elements)
Surface 3 (modals):   #30363D  (dropdowns, popovers)
Text Primary:         #F0F6FC  (warm off-white, NOT pure white)
Text Secondary:       #8B949E  (muted labels)
Border:               rgba(240,246,252,0.06)  (barely visible structure)
Accent Cyan:          #58A6FF  (softer, more professional than #00f0ff)
Accent Purple:        #BC8CFF  (softer lavender, not neon)
Accent Pink:          #F778BA  (danger/destructive)
Success:              #3FB950
Warning:              #D29922
```

> [!IMPORTANT]
> These are more **muted and professional** than the current neon palette. The current UI looks "AI-generated" partly because of the aggressive neon cyan/purple. Real premium tools use **softer, more restrained accents**.

#### 3. Layout Architecture Overhaul

**Current:** `header | [canvas] [right-column(4 panels)]`

**New:** `top-bar | left-rail(48px) | canvas-area(flex) | right-sidebar(380px)`

- **Top Bar** (48px): Logo + status badges + system info — thinner, more minimal
- **Left Rail** (48px): Vertical icon-only navigation — Draw/Move/Erase modes, Element picker, Bond type selector, Clear. Inspired by Ketcher's left toolbar
- **Central Canvas** (flex, maximized): Drawing area with refined grid, SMILES input bar at bottom
- **Right Sidebar** (380px): Stacked panels — PyMOL Chat, MDRepo Predictions, PDB Targets, Checkpoint Log. Each with collapsible headers

#### 4. Panel Design Refinement
- **Elevation-based depth** instead of glassmorphism-heavy approach — each nested layer is slightly lighter
- **1px borders** using `rgba(240,246,252,0.06)` — barely visible structural lines
- **Rounded corners**: 12px (panels), 8px (buttons), 6px (inputs)
- **No heavy `box-shadow`** — use border + subtle background shift for depth
- **Panel headers**: Smaller (40px), left-aligned title, right-aligned badge/status

#### 5. Toolbar Redesign (Left Rail)
- Vertical pill-shaped icon buttons (36×36px)
- Active state: filled background with soft accent color + left border indicator
- Hover state: subtle background lighten
- Grouped with thin divider lines between sections (Mode | Element | Bond | Actions)
- Element buttons show colored dots (CPK-standard) instead of plain letters

#### 6. Micro-Animations & Polish
- Panel entrance: `opacity 0→1, translateY(8px→0)` over 300ms, staggered by 50ms
- Button hover: `transform: translateY(-1px)` + background lighten over 150ms
- Active tool indicator: left border slides in (`scaleY(0→1)`) over 200ms
- Canvas grid: softer opacity (`rgba(255,255,255,0.015)`)
- Logo pulse animation: slower (3s), more subtle scale (1.0→1.08)
- Scrollbar: 4px width (thinner), rounded

#### 7. Data Table Styling
- Tabular figures enabled: `font-feature-settings: 'tnum' 1`
- Alternating row backgrounds using elevation layers (not stripe colors)
- Colorblind-safe palette for variance indicators (Okabe-Ito)
- Compact padding (6px 10px) for data-dense views

#### 8. SMILES Input Bar Redesign
- Integrated into bottom of canvas area (not separate box)
- Wider input with monospace font
- "Render" button uses accent gradient, pill-shaped
- Subtle focus ring animation

---

## What Stays Untouched

> [!NOTE]
> The following are NOT modified at all:
> - All `taipy:input`, `taipy:text`, `taipy:button` bindings (lines 588-689)
> - All JavaScript canvas engine code (lines 690-1211)
> - All CSS class names referenced by `kinetic_sketch.py` (`checkpoint-log-line`, `checkpoint-time`, `checkpoint-success`, `checkpoint-warning`, `pymol-code-block`, `variance-indicator`, `predictions-table`, `repurposing-table`, `message-user`, `message-system`, etc.)
> - The Taipy bridge architecture (hidden inputs + visible styled replicas)

---

## Verification Plan

### Automated Tests
```bash
# Verify the server starts without HTML parsing errors
venv/bin/python kinetic_sketch.py
# Open http://127.0.0.1:5001 and verify no JSX errors in browser console
```

### Manual Verification
- Open in Incognito window to bypass all caches
- Verify canvas drawing (add atoms, bonds, erase) works
- Verify SMILES input renders correctly
- Verify all 4 right panels display their Taipy-bound content
- Verify chat input sends messages
- Check responsive behavior on different screen widths
