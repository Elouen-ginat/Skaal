# Skaal Design System

The live docs now run on the integrated Skaal design system shipped in this folder. The new system combines a semantic token foundation, a landing-page composition reference, and a local preview library of HTML specimens that match the live docs theme.

## Foundation

- [tokens/colors_and_type.css](tokens/colors_and_type.css): the semantic design foundation for color, type, spacing, surfaces, and motion.
- [tokens/skaal-tokens.css](tokens/skaal-tokens.css): the docs entry point that exposes the foundation to MkDocs and keeps the compatibility aliases used by the current site.
- [styles/landing.css](styles/landing.css): the shared landing component layer used by both the live homepage and the preview reference.
- [preview/landing-page.html](preview/landing-page.html): the integrated landing reference.
- [preview/landing.css](preview/landing.css): the preview-only adapter for the standalone landing reference shell.
- [../assets/stylesheets/extra.css](../assets/stylesheets/extra.css): the MkDocs adaptation layer that applies the new system to the docs shell and content pages.

## System Language

- Constraint-first surfaces: code, plans, candidate cards, and runtime artifacts should feel central instead of decorative.
- Resolved infrastructure paths: motion and accent color should reinforce selection, evaluation, and explicit outcomes.
- Tool-grade clarity: typography, spacing, and component states should read like infrastructure software, not generic SaaS marketing.
- One language across docs and references: the homepage, guides, and preview specimens should all feel like the same product system.

## Preview Library

- Controls and forms: [buttons.html](preview/buttons.html), [forms.html](preview/forms.html).
- Planning surfaces: [cards.html](preview/cards.html), [backend-card.html](preview/backend-card.html), [plan-graph.html](preview/plan-graph.html), [terminal-block.html](preview/terminal-block.html), [code-surface.html](preview/code-surface.html).
- Status and tokens: [chips-constraint.html](preview/chips-constraint.html), [status-signals.html](preview/status-signals.html).
- Visual language: [patterns.html](preview/patterns.html), [motion.html](preview/motion.html), [radii.html](preview/radii.html), [shadows.html](preview/shadows.html), [spacing-scale.html](preview/spacing-scale.html).
- Brand and type: [icons.html](preview/icons.html), [logo-marks.html](preview/logo-marks.html), [logo-primary.html](preview/logo-primary.html), [type-headings.html](preview/type-headings.html), [type-body.html](preview/type-body.html), [type-families.html](preview/type-families.html).
- Palette references: [colors-core.html](preview/colors-core.html), [colors-accent.html](preview/colors-accent.html), [colors-semantic.html](preview/colors-semantic.html), [colors-tints.html](preview/colors-tints.html).

## When To Use It

- Use this system when a docs page or demo should look like the shipped Skaal site instead of a generic framework theme.
- Use the preview files when you need a precise component reference before adapting something into the live docs shell.
- Use [ASSETS.md](ASSETS.md) for the full linked inventory of the integrated preview library and the published SVG asset pack.
