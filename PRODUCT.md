# Product

## Users

Platform and ML engineers who run retrieval (RAG) for many customers, one index per
customer, and watch their vector database bill grow with tenants who rarely query.
Also the AI coding agents they point at this repo to adapt it. Their context: they
need to decide how long an idle tenant may stay in memory, and want that decision
backed by measured restore cost rather than a guess.

## Product Purpose

A multi-tenant RAG service that serves hot tenants from Qdrant, parks idle tenants'
collections as verified snapshots in Backblaze B2, restores them on the next query,
and measures what that costs in latency and saves in memory. Success = an engineer
runs the demo, parks and restores a tenant, reads the latency report, and can set a
parking threshold on numbers; and trusts that parking never loses a tenant's data.

## Maturity and Support Boundary

This is a maintained open-source sample, not a complete hosted SaaS product.
It is built with production-minded controls and can be adapted for production use with
caution, but adopters own product-specific validation, security, deployment, and
operations. Repository defects and feature requests go through the public GitHub issue
tracker; B2 account, billing, service, and API questions go through Backblaze Support.
The template/sample itself is not covered by the Backblaze service level agreement,
and no SLA is provided for the repository software.

## Brand Personality

Confident, precise, quietly professional. Voice is direct and free of hype ("Keep
vector memory for the tenants who query; park the rest in B2"). The interface should
feel like an operator's tool — considered, calm, trustworthy — and always say where a
tenant lives (hot, parked, empty) and what an action will cost before it runs.

## Anti-references

- **Generic AI/SaaS slop.** No gradient text, hero-metric templates, identical
  icon-card grids, tracked uppercase eyebrows, or decorative glassmorphism. These are
  the exact 2026 AI tells this sample avoids.
- **Over-branded / loud.** No heavy brand-color drenching, decorative motion, or flashy
  effects.
- **Toy / prototype feel.** No missing states, inconsistent components, or placeholder
  polish. Must read as polished, dependable scaffolding.
- **Enterprise-drab.** No Bootstrap-era gray boxes or dense-but-lifeless admin-panel
  look. Considered, like modern dev tools (Linear, GitHub Primer, Stripe).

## Design Principles

- **Show the cost before the action.** Parking, restoring and pruning say what they
  will do (dry run first) and report what they did, including any reason a tenant
  stayed hot.
- **Neutral foundation, easy to rebrand.** Identity lives in tokens (`globals.css`) and
  one config file. Screens are built from the shared UI kit so a rebrand is a token
  swap, not a rewrite.
- **Earned familiarity over novelty.** Use standard, trusted affordances (top bar +
  side nav, command palette, data tables). The tool disappears into the task.
- **Every state is designed.** Default, hover, focus, active, disabled, loading (skeleton),
  empty (teaches the interface), and error (says what's wrong + offers retry) — never
  half-shipped.
- **Consistency is the feature.** One button vocabulary, one form-control set, one icon
  style across every screen. Divergence is a bug.

## Accessibility & Inclusion

Target **WCAG 2.1 AA**. Body text ≥ 4.5:1, large/bold text ≥ 3:1, visible focus
indicators on every interactive element, full keyboard navigation, correct semantic
landmarks and heading order, labelled form controls, and a `prefers-reduced-motion`
alternative for every animation. Full light and dark theme parity.
