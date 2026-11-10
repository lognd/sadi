+++
id = "01M71KE5ENACTPQ56XAWW37VH5"
title = "UI design system: modern themed app shell, wizard, panels, doctor"
type = "task"
category = "in-progress"
priority = "high"
points = 8
reporter = "lognd"
created = "2026-11-10T02:08:49Z"
updated = "2026-11-10T02:12:44Z"
labels = ["model:sonnet"]
scope = ["web/src/styles.css", "web/src/App.tsx", "web/src/components/**", "web/src/screens/**", "web/src/doctor/**", "web/index.html", "docs/web/**", "web/src/a11y/**"]

[[acceptance]]
text = "web/src/styles.css becomes a design system: CSS custom-property tokens (color, space, radius, shadow, type scale), light and dark themes via prefers-color-scheme plus a manual toggle persisted in localStorage, system font stack, focus rings, cards, buttons, inputs, tables, badges"
bound = true

[[acceptance]]
text = "App shell: header with brand, backend status pill and theme toggle; centered max-width content; step rail and wizard shell restyled; GuidancePanel, results, budget and Doctor screens use the shared tokens (no ad hoc inline colors)"
bound = true

[[acceptance]]
text = "Accessible: AA contrast in both themes, visible keyboard focus, reduced-motion respected; existing vitest suites and the e2e specs still pass; npm run build and typecheck clean"
bound = true
+++

The user says the app looks like garbage; make it look polished and professional for a lab instrument UI. Standards: ASCII only, no emojis, NEVER a Co-Authored-By line; docs updated in the same change; frontend tests (vitest) where logic exists; no new heavy UI deps unless justified (self-hosted fonts only, no CDN).
