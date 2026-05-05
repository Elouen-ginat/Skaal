# Skaal Design System Assets

This inventory is derived from the design board in [docs/design_system/design_asset.png](design_asset.png) and the direction documented in [docs/design_system/README.md](README.md).

## Brand Core

| Asset | File | Purpose |
|---|---|---|
| Primary logo lockup | [docs/design_system/skaal-logo.svg](skaal-logo.svg) | Main brand signature for docs, decks, and hero surfaces |
| Chosen logo mark | [docs/design_system/logo_variants/it-dot.svg](logo_variants/it-dot.svg) | Canonical standalone symbol |
| Wide mark | [docs/design_system/logo_variants/it-dot-wide.svg](logo_variants/it-dot-wide.svg) | Spacious placements and overview compositions |
| Tight mark | [docs/design_system/logo_variants/it-dot-tight.svg](logo_variants/it-dot-tight.svg) | Dense placements and small utility contexts |
| Alternate cut mark | [docs/design_system/logo_variants/cut-rail.svg](logo_variants/cut-rail.svg) | Expresses evaluation and narrowing |
| Alternate step mark | [docs/design_system/logo_variants/step-rail.svg](logo_variants/step-rail.svg) | Expresses staged progression |
| Alternate linked mark | [docs/design_system/logo_variants/linked-rail.svg](logo_variants/linked-rail.svg) | Expresses connected system topology |
| Logo contact sheet | [docs/design_system/logo_variants/overview.svg](logo_variants/overview.svg) | Side-by-side comparison for review |
| Favicon | [docs/design_system/favicon.svg](favicon.svg) | Browser tab and bookmark usage |
| App icon | [docs/design_system/app-icon.svg](app-icon.svg) | Desktop and launcher usage |

## Iconography

| Asset | File | Purpose |
|---|---|---|
| Icon sprite sheet | [docs/design_system/icons/sprite.svg](icons/sprite.svg) | Source definitions for UI/product icons |
| Iconography overview | [docs/design_system/icons/iconography.svg](icons/iconography.svg) | Review sheet for the icon family |

Included icons: Constraints, Solver, Plan Graph, Selected Route, Compute, Storage, Blob, Database, Vector, Schedule, Deploy, Target.

## UI Components

| Asset | File | Purpose |
|---|---|---|
| Constraint token set | [docs/design_system/components/constraint-tokens.svg](components/constraint-tokens.svg) | Constraint badges and spec-token styling |
| Backend card | [docs/design_system/components/backend-card.svg](components/backend-card.svg) | Evaluated backend card example |
| Status signals | [docs/design_system/components/status-signals.svg](components/status-signals.svg) | Resolved, deploying, degraded, and error states |
| Plan graph example | [docs/design_system/components/plan-graph-example.svg](components/plan-graph-example.svg) | Signature planner component |
| Pulumi output panel | [docs/design_system/components/pulumi-output.svg](components/pulumi-output.svg) | Generated artifact/code block treatment |
| Terminal block | [docs/design_system/components/terminal-block.svg](components/terminal-block.svg) | CLI/observability surface styling |
| Badge set | [docs/design_system/components/badges.svg](components/badges.svg) | Product, platform, and stack badges |

## Patterns and Diagrams

| Asset | File | Purpose |
|---|---|---|
| Grid light | [docs/design_system/patterns/grid-light.svg](patterns/grid-light.svg) | Quiet background surface for light UI |
| Dot field | [docs/design_system/patterns/grid-dots.svg](patterns/grid-dots.svg) | Technical dotted field background |
| Grid dark | [docs/design_system/patterns/grid-dark.svg](patterns/grid-dark.svg) | Terminal/dashboard dark surface |
| Aurora gradient | [docs/design_system/patterns/aurora-gradient.svg](patterns/aurora-gradient.svg) | Accent background treatment |
| Inline graph | [docs/design_system/diagrams/nodes-inline.svg](diagrams/nodes-inline.svg) | Simple route-and-node diagram |
| Resolve flow | [docs/design_system/diagrams/flow-resolve.svg](diagrams/flow-resolve.svg) | Constraint to backend selection flow |
| Network route | [docs/design_system/diagrams/network-route.svg](diagrams/network-route.svg) | Radial system graph with resolved endpoint |

## Illustrations

| Asset | File | Purpose |
|---|---|---|
| Code console | [docs/design_system/illustrations/code-console.svg](illustrations/code-console.svg) | Developer tooling hero/support art |
| Stack cubes | [docs/design_system/illustrations/stack-cubes.svg](illustrations/stack-cubes.svg) | Infrastructure stack illustration |
| Cloud route | [docs/design_system/illustrations/cloud-route.svg](illustrations/cloud-route.svg) | Hybrid local/cloud flow illustration |
| Analytics screen | [docs/design_system/illustrations/analytics-screen.svg](illustrations/analytics-screen.svg) | Dashboard/support illustration |

## Tokens

| Asset | File | Purpose |
|---|---|---|
| CSS token file | [docs/design_system/tokens/skaal-tokens.css](tokens/skaal-tokens.css) | Colors, typography, radii, stroke widths, and motion timing |

## Web-Sourced Foundations

The type stack is backed by open web fonts available from Google Fonts:

- Space Grotesk for headings
- IBM Plex Sans for body copy
- IBM Plex Mono for code and terminal surfaces

These are wired into [docs/design_system/tokens/skaal-tokens.css](tokens/skaal-tokens.css) using a single `@import` statement for fast reuse in docs or demos.
