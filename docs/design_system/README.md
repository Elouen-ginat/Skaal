# Skaal Design System

Skaal should not present as a generic cloud toolkit. The product direction in this repository is sharper than that: declare constraints, solve infrastructure, generate artifacts, and move between local and cloud targets without rewriting application code.

This design system translates that product shape into a visual language.

## Brand Direction

**Brand idea:** bounded systems, resolved routes, auditable decisions.

**Tone:** technical, modern, calm, exact.

**Primary metaphor:** a constrained frame containing one selected route.

That metaphor matches Skaal's core workflow:

1. Developers declare constraints rather than hard-code infrastructure.
2. The solver evaluates available backends.
3. Skaal selects the cheapest viable path.
4. The system generates deployment artifacts for the chosen target.

The resulting identity should feel more like a planning engine or observability tool than a generic SaaS framework.

## Design Principles

### 1. Constraint-First

Interfaces should visually emphasize inputs, requirements, and capabilities before outcomes. Constraint badges, capability tables, and plan views should feel central rather than secondary.

### 2. Resolved, Not Decorative

Motion, color, and composition should suggest computation and selection. Avoid ornamental effects that do not reinforce routing, planning, or verification.

### 3. Local to Cloud Continuity

Skaal bridges local development, generated artifacts, and cloud deployment. The visual system should feel coherent across CLI docs, runtime UI, dashboards, and deployment diagrams.

### 4. Tool-Grade Clarity

This is infrastructure software. Typography, spacing, and component states should prioritize readability and precision over marketing softness.

## Color System

### Core Palette

| Token | Hex | Use |
|---|---|---|
| Ink | `#0E1726` | Primary text, outlines, dark UI surfaces |
| Mist | `#F6FBF9` | Backgrounds, negative space, light surfaces |
| Grid | `#A7B4C2` | Dividers, grid lines, secondary strokes |
| Signal Teal | `#13B5A8` | Primary accent, route highlights, active controls |
| Solver Green | `#9AE66E` | Success, resolved plan state, selected path completion |
| Cloud Blue | `#5FA8FF` | Target/platform accents, links, info states |
| Rust Copper | `#C96A3D` | Warnings, fallbacks, migration or compatibility states |

### Usage Rules

- Ink and Mist should carry most of the interface.
- Teal and Solver Green are the primary brand accents.
- Cloud Blue is reserved for platform or informational emphasis.
- Copper is used sparingly for warnings, degradations, or migration-specific communication.

## Typography

### Primary Families

- Headings: Space Grotesk
- Body: IBM Plex Sans
- Code and CLI surfaces: IBM Plex Mono

### Typographic Character

- Headlines should feel structural and intentional, not editorial.
- Body copy should remain neutral and highly readable.
- Code samples, manifests, and plan output should use a monospace face consistently.

## Layout and Shape Language

- Prefer structured grids and disciplined whitespace.
- Use rounded rectangles with moderate radii in the 14px to 16px range.
- Use thin technical strokes in the 1.5px to 2px range where possible.
- Favor frames, route lines, nodes, and beveled or hex-adjacent containers over generic cards.
- Backgrounds should support the system with subtle gradients, graph patterns, or grid structures rather than flat fills.

## Component Direction

### Constraint Tokens

Constraint badges should look like specification tokens, not marketing chips. Each token should communicate a category such as latency, durability, throughput, access pattern, or scale.

### Backend Cards

Backend cards should expose capability bars, target support, and cost or suitability indicators. Cards should read like evaluated options in a planner, not like ecommerce tiles.

### Plan Graph

The plan graph is a signature component. It should highlight the chosen route while still acknowledging alternative paths. Color and motion should make the final resolved path obvious.

### Code and Manifest Blocks

Use Ink backgrounds with high-contrast text and accent highlights for selected lines, tokens, or generated outputs. These areas should feel close to terminal and observability tooling.

## Motion

- Motion should suggest graph resolution, route drawing, or node activation.
- Keep timing short and crisp, typically 140ms to 220ms.
- Avoid floaty animations or excessive spring behavior.
- Use animation to reinforce state change and selected infrastructure paths.

## Asset Inventory

The complete design-system asset pack now lives alongside this document and is organized into these folders:

- `logo_variants/` for the chosen `it-dot` symbol family and comparison sheets
- `icons/` for the product iconography set
- `components/` for UI primitives and showcase surfaces
- `patterns/` for background treatments
- `diagrams/` for graph and route visuals
- `illustrations/` for hero and product-support renders
- `tokens/` for reusable CSS design tokens

See [docs/design_system/ASSETS.md](ASSETS.md) for the full file list.

## Logo System

The selected direction is the `it-dot` mark: a frameless symbol built from an angled rail and a selected endpoint.

### Meaning

- The paired rails represent declared constraints or parallel infrastructure options.
- The green endpoint represents the selected outcome.
- Small shifts in alignment are used to imply routing, evaluation, or resolution.
- Motion, when used, should reinforce selection rather than dominate the mark.

### Construction

- Core geometry: two horizontal capsules plus one circular endpoint.
- Static state: each mark must read clearly at favicon size without motion.
- Differentiation: asymmetry, offsets, cut-ins, or a light structural rail can prevent the burger-menu reading.
- Color treatment: Ink for the rails and Solver Green for the selected endpoint.

### Available Logo Assets

- [docs/design_system/skaal-logo.svg](skaal-logo.svg): primary horizontal lockup using the chosen `it-dot` mark.
- [docs/design_system/logo_variants/it-dot.svg](logo_variants/it-dot.svg): canonical standalone symbol.
- [docs/design_system/logo_variants/it-dot-wide.svg](logo_variants/it-dot-wide.svg): more open variant for hero and signage layouts.
- [docs/design_system/logo_variants/it-dot-tight.svg](logo_variants/it-dot-tight.svg): denser icon variant for compact use.
- [docs/design_system/logo_variants/cut-rail.svg](logo_variants/cut-rail.svg): sharper evaluative version with cut-facing terminals.
- [docs/design_system/logo_variants/step-rail.svg](logo_variants/step-rail.svg): stepped variation suggesting staged resolution.
- [docs/design_system/logo_variants/linked-rail.svg](logo_variants/linked-rail.svg): system-oriented variation with a connected spine.
- [docs/design_system/logo_variants/overview.svg](logo_variants/overview.svg): side-by-side contact sheet for the finalized family.
- [docs/design_system/favicon.svg](favicon.svg): dark-surface favicon export.
- [docs/design_system/app-icon.svg](app-icon.svg): light-surface application icon export.

## Implementation Notes

This system is intended to work across:

- documentation pages
- generated product pages or demo sites
- diagrams and slide decks
- runtime dashboards
- CLI screenshots and developer education assets

The design system now includes those next-step foundations as shipped assets: CSS tokens, component references, and icon/logo exports for browser and app surfaces.
