# Skaal Design System Inventory

This inventory now covers both the published `design_system/` assets and the newly added source materials that define the refreshed docs theme.

## Foundation Files

| Asset | File | Purpose |
|---|---|---|
| Published token entry point | [skaal-tokens.css](tokens/skaal-tokens.css) | Token file loaded by the docs site |
| Integrated foundation source | [colors_and_type.css](tokens/colors_and_type.css) | Semantic color and typography source now shipped inside the design system |
| Shared landing component layer | [landing.css](styles/landing.css) | Canonical landing components consumed by both MkDocs and the preview reference |
| Landing reference HTML | [landing-page.html](preview/landing-page.html) | Canonical layout reference for the docs homepage refresh |
| Landing preview adapter | [landing.css](preview/landing.css) | Preview-only shell styles layered on top of the shared landing component CSS |

## Preview Library

All preview files now live under `docs/design_system/preview/`.

| Preview | File | Purpose |
|---|---|---|
| Shared preview card wrapper | [_card.css](preview/_card.css) | Base frame for the HTML previews |
| Buttons | [buttons.html](preview/buttons.html) | Primary, accent, secondary, ghost, and danger button states |
| Cards | [cards.html](preview/cards.html) | Step-card structure and kicker treatment |
| Backend card | [backend-card.html](preview/backend-card.html) | Evaluated backend candidate surface |
| Constraint chips | [chips-constraint.html](preview/chips-constraint.html) | Constraint badge vocabulary |
| Code surface | [code-surface.html](preview/code-surface.html) | Dark code panel styling |
| Terminal block | [terminal-block.html](preview/terminal-block.html) | CLI and observability surface |
| Plan graph | [plan-graph.html](preview/plan-graph.html) | Selected-route and candidate visualization |
| Forms | [forms.html](preview/forms.html) | Input, field, and control treatment |
| Icons | [icons.html](preview/icons.html) | Icon-set review sheet |
| Landing page reference | [landing-page.html](preview/landing-page.html) | Fully integrated landing reference using the local preview assets |
| Landing preview adapter | [landing.css](preview/landing.css) | Preview-only CSS used by the local landing shell |
| Logo marks | [logo-marks.html](preview/logo-marks.html) | Mark comparisons and symbol direction |
| Primary logo | [logo-primary.html](preview/logo-primary.html) | Full lockup review |
| Patterns | [patterns.html](preview/patterns.html) | Background and grid treatments |
| Status signals | [status-signals.html](preview/status-signals.html) | Resolved, warning, and operational states |
| Motion | [motion.html](preview/motion.html) | Timing and transition direction |
| Radii | [radii.html](preview/radii.html) | Corner system reference |
| Shadows | [shadows.html](preview/shadows.html) | Elevation reference |
| Spacing scale | [spacing-scale.html](preview/spacing-scale.html) | 4px spacing system |
| Type families | [type-families.html](preview/type-families.html) | Font-family decisions |
| Type headings | [type-headings.html](preview/type-headings.html) | Display, h1, h2, and heading rhythm |
| Type body | [type-body.html](preview/type-body.html) | Body copy and supporting text |
| Core colors | [colors-core.html](preview/colors-core.html) | Base palette |
| Accent colors | [colors-accent.html](preview/colors-accent.html) | Accent and signal colors |
| Semantic colors | [colors-semantic.html](preview/colors-semantic.html) | Foreground and background roles |
| Color tints | [colors-tints.html](preview/colors-tints.html) | Supporting tints and transparency treatment |

## Published SVG Asset Pack

These assets still ship from the existing `docs/design_system/` folder and are used directly by the docs content.

### Brand Core

| Asset | File | Purpose |
|---|---|---|
| Primary logo lockup | [skaal-logo.svg](skaal-logo.svg) | Main brand signature for docs and supporting surfaces |
| Logo mark | [logo_variants/it-dot.svg](logo_variants/it-dot.svg) | Canonical standalone symbol |
| Wide mark | [logo_variants/it-dot-wide.svg](logo_variants/it-dot-wide.svg) | Spacious hero and signage placements |
| Tight mark | [logo_variants/it-dot-tight.svg](logo_variants/it-dot-tight.svg) | Compact placements |
| Comparison sheet | [logo_variants/overview.svg](logo_variants/overview.svg) | Logo review board |
| Favicon | [favicon.svg](favicon.svg) | Browser tab usage |
| App icon | [app-icon.svg](app-icon.svg) | Launcher and icon surfaces |

### Components

| Asset | File | Purpose |
|---|---|---|
| Constraint tokens | [components/constraint-tokens.svg](components/constraint-tokens.svg) | Constraint badge sheet |
| Backend card | [components/backend-card.svg](components/backend-card.svg) | Backend evaluation illustration |
| Plan graph example | [components/plan-graph-example.svg](components/plan-graph-example.svg) | Planner route visualization |
| Pulumi output | [components/pulumi-output.svg](components/pulumi-output.svg) | Generated artifact panel |
| Terminal block | [components/terminal-block.svg](components/terminal-block.svg) | Command-line visual |
| Status signals | [components/status-signals.svg](components/status-signals.svg) | Operational-state illustrations |

### Patterns, Diagrams, and Illustrations

| Asset | File | Purpose |
|---|---|---|
| Grid light | [patterns/grid-light.svg](patterns/grid-light.svg) | Primary light-surface background grid |
| Grid dark | [patterns/grid-dark.svg](patterns/grid-dark.svg) | Dark-surface grid |
| Dot field | [patterns/grid-dots.svg](patterns/grid-dots.svg) | Secondary technical pattern |
| Resolve flow | [diagrams/flow-resolve.svg](diagrams/flow-resolve.svg) | Constraint-to-selection diagram |
| Network route | [diagrams/network-route.svg](diagrams/network-route.svg) | Resolved endpoint diagram |
| Code console | [illustrations/code-console.svg](illustrations/code-console.svg) | Support art for tooling surfaces |
| Stack cubes | [illustrations/stack-cubes.svg](illustrations/stack-cubes.svg) | Infrastructure stack illustration |
| Cloud route | [illustrations/cloud-route.svg](illustrations/cloud-route.svg) | Local-to-cloud motion illustration |
| Analytics screen | [illustrations/analytics-screen.svg](illustrations/analytics-screen.svg) | Dashboard support art |
