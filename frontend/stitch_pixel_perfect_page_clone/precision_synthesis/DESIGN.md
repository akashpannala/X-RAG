---
name: Precision Synthesis
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#3f484c'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#6f797c'
  outline-variant: '#bfc8cc'
  surface-tint: '#10677c'
  primary: '#005365'
  on-primary: '#ffffff'
  primary-container: '#1a6c81'
  on-primary-container: '#adeaff'
  inverse-primary: '#8ad1e8'
  secondary: '#505f76'
  on-secondary: '#ffffff'
  secondary-container: '#d0e1fb'
  on-secondary-container: '#54647a'
  tertiary: '#434b61'
  on-tertiary: '#ffffff'
  tertiary-container: '#5b6379'
  on-tertiary-container: '#d8e0fa'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b3ebff'
  primary-fixed-dim: '#8ad1e8'
  on-primary-fixed: '#001f27'
  on-primary-fixed-variant: '#004e5f'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#dae2fd'
  tertiary-fixed-dim: '#bec6e0'
  on-tertiary-fixed: '#131b2e'
  on-tertiary-fixed-variant: '#3f465c'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.025em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system is tailored for an enterprise retrieval-augmented generation (RAG) workbench and research workspace. It addresses technical knowledge workers, data scientists, engineers, and enterprise analysts who require absolute confidence in machine-synthesized intelligence. 

The aesthetic marries **Minimalism** with an exacting **Modern / Developer Tool** rigor inspired by clean component-first primitives. Visual density is calibrated for high information throughput: sharp boundaries, subdued neutrals, purposeful typography, and hairline delineations replace gratuitous ornamentation. The interface evokes stability, high throughput, and cognitive clarity, ensuring the user remains in an uninterrupted synthesis state across dense document corpora, multi-hop reasoning trees, and grounded citations.

## Colors

The palette employs high-contrast, mathematically robust pairings adhering strictly to WCAG 2.2 AA and AAA standards for readability.

- **Primary / Accent (`#1A6C81`)**: A disciplined cyan-slate teal used for focused states, active navigation tabs, interactive citation markers, primary submission buttons, and context-selection badges.
- **Secondary (`#64748B`)**: Slate ink reserved for secondary labels, document metadata, file sizes, retrieval scores, and non-blocking iconography.
- **Tertiary / Core Ink (`#0F172A`)**: Deep slate obsidian for maximum contrast text rendering on white and light slate canvases.
- **Neutral Canvas (`#F8FAFC`)**: A pale slate background that establishes ambient workspace warmth, separating utility toolbars from elevated content cards (`#FFFFFF`).
- **Borders & Separators (`#E2E8F0`)**: Hairline structure defining panes, inspector flyouts, and modular grids.
- **Feedback & State Semantic Tokens**:
  - Success (`#15803D`): Grounding verification, vector sync confirmations, completed embeddings.
  - Warning (`#B45309`): High token consumption alerts, low retrieval similarity warnings.
  - Danger (`#B91C1C`): Hallucination warnings, ungrounded answers, deletion actions.

## Typography

The typographic hierarchy prioritizes rapid scanning and structural density. 

- **Geist** serves as the primary system face for all structural interfaces, document bodies, conversation threads, and headings. Its geometric neutrality and tight metrics prevent layout shifting across dense tables and multi-column panels.
- **JetBrains Mono** is employed functionally for high-precision utility tasks: inline citation tags (`[1]`, `[doc_4]`), confidence percentages, chunk boundary IDs, latency metrics, and API payloads. 

Headings maintain subtle negative tracking to preserve cohesion at scale, while mono-spaced tokens preserve visual baseline alignment inside tabular cards and citation callouts.

## Layout & Spacing

The layout is built around a multi-panel desktop workbench composed of three distinct functional areas:
1. **Source Navigator (Collapsible Drawer / Rail)**: Width 280px–340px, pinned left.
2. **Synthesis Engine / Notebook (Fluid Canvas)**: Auto-flex middle region for generation and comparative analysis.
3. **Inspector & Vector Grounding Pane**: Width 380px–460px, pinned right for side-by-side verification.

The layout adapts across viewports:
- **Desktop (>=1280px)**: Three-column persistent layout with 16px (`gutter`) splits between columns, anchored by full-height border dividers.
- **Tablet (768px - 1279px)**: Two-column layout with the Inspector pane converted into a sliding off-canvas sheet or persistent overlay; Source Navigator condenses to an icon rail.
- **Mobile (<768px)**: Single stacked view utilizing a segmented control to switch sequentially between Sources, Chat, and Grounding Citations.

## Elevation & Depth

This system avoids blurred drop shadows and heavy multi-tiered drops, adopting a **low-contrast outline and flat-tonal hierarchy**:

- **Layer 0 (Canvas Base)**: `#F8FAFC` — Acts as the ambient workspace foundation.
- **Layer 1 (Card & Panel Surface)**: `#FFFFFF` — All interactive working zones, panels, conversation logs, and sidebars sit flush on Layer 0, delineated by a 1px solid border (`#E2E8F0`).
- **Layer 2 (Overlays & Modals)**: `#FFFFFF` with an ultralight structural boundary (`border: 1px solid #CBD5E1`) and a single micro-shadow (`0 4px 6px -1px rgba(15, 23, 42, 0.05), 0 2px 4px -2px rgba(15, 23, 42, 0.03)`).
- **Interactive Depth**: Elevation change is communicated via border color changes (e.g., `#E2E8F0` transitioning to `#1A6C81` on focus) rather than artificial vertical lift or expanding shadow radii.

## Shapes

The design system standardizes on a **6px radius** (`rounded-md` equivalent in standard utility sets), matching clean modern developer tools. 

- Interactive buttons, form inputs, tooltips, dialogs, and citation chips share a consistent `0.375rem` (6px) curvature.
- Large container surfaces and main structural viewport frames enforce the identical radius, preserving clean orthogonal lines.
- Micro-elements such as status indicators or vector badge counters retain geometric discipline without using pill or circular contours.

## Components

### Buttons
- **Primary**: Solid `#1A6C81` background, `#FFFFFF` text, 6px radius, hover state `#145566`. Active state scales subtly (`0.98`).
- **Secondary / Outline**: `#FFFFFF` background, `#0F172A` text, 1px solid `#E2E8F0`, hover state `#F8FAFC` with `#CBD5E1` border.
- **Ghost**: Transparent background, `#64748B` text, hover state `#F1F5F9` with `#0F172A` text.
- **Sizes**: Heights fixed at 32px (compact/workbench default) and 40px (default), padding `0 12px` and `0 16px`.

### Citation Chips & Reference Badges
- Displayed inline within synthesized answers.
- Set in **JetBrains Mono** (`label-md` or `label-sm`), featuring `#F1F5F9` background, `#1A6C81` text, and a crisp hairline border (`#E2E8F0`).
- Hover shifts the background to `#E0F2FE` with a border transition to `#1A6C81`. Clicking scrolls the pinned Inspector pane directly to the bounding box of the source document.

### Input Fields & Search Bars
- Background `#FFFFFF`, 1px solid border `#E2E8F0`, text `#0F172A`, placeholder `#94A3B8`.
- Focus state: Outline none, border set to `#1A6C81`, accompanied by a uniform 1px ring in `#1A6C81`.
- Sizing conforms to button dimensions for horizontal pairing in prompt execution bars.

### Cards & Document Nodes
- Background `#FFFFFF`, border `1px solid #E2E8F0`, 6px radius.
- Padding set to 12px or 16px.
- Selected state (e.g., active source file for context injection) displays a left-accent indicator: `border-l-2 border-l-[#1A6C81]`.

### Checkboxes & Radios
- Square 16px dimensions with a 4px corner radius for checkboxes, circular for radios.
- Unchecked: `#FFFFFF` with `#CBD5E1` border.
- Checked: `#1A6C81` with `#FFFFFF` checkmark or center pin.

### Lists & Chunk Inspector Rows
- Hoverable horizontal rows with alternating or single `#FFFFFF` states.
- Hover reveals an inline action shelf (copy text, exclude chunk, inspect embeddings).
- Metadata badges (token count, similarity score like `0.89 sim`) rendered in `JetBrains Mono` at `label-sm`.