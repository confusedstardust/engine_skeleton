# NarAgent practice UI — sidebar/component consolidation (phase 1)

## Scope and status

This change is **implemented in a review branch**, not independently verified or deployed. Reference: `linchangWeb/main`'s `src/components/teacher-plaza-header.tsx` and `src/app/teacher-plaza.css` (teacher resource plaza). The app-specific NarAgent route remains `forge_frontend_next/app/practice/`.

The original practice sidebar duplicated five hand-drawn SVGs, a text-based "N" logo, navigation UI and account placement. That created both visual drift and a second implementation to maintain.

## Reuse decisions

- **Brand:** `forge_frontend_next/components/brand-logo.tsx`, already backed by `@narrativeos/ui/brand-logo`; no replacement logo/SVG.
- **Account:** `forge_frontend_next/components/account-menu.tsx` adapts the existing shared `@narrativeos/ui` menu's `dock` option; no second account/session implementation. The menu now lives at the foot of the sidebar.
- **Buttons:** `components/ui/button.tsx`; no new button state/loading primitive.
- **Icons:** `lucide-react` version matched to the portal, rather than a per-page SVG switch.
- **Navigation shell:** `components/ui/workspace-sidebar.tsx` and its CSS module are reusable *within Forge*. It accepts route data, main action, custom content and footer; it owns presentation, accessible names and collapse control.
- **Practice adapter:** `app/practice/practice-navigation.tsx` owns only recent-work fetching, routes and workbench-specific action. It does not own the shared UI shell.
- **Layout:** `resizable-workspace.tsx` manages the collapsed-state width and persists it alongside existing per-user split ratios. On mobile the collapsed sidebar becomes a narrow left rail.
- **Routing:** Next.js internal links use `Link` (which applies Forge's `basePath`); the plaza is an external anchor. Existing work IDs are encoded as query parameters.

## Boundaries and next phase

This is **not yet a shared sidebar release across both repositories**. The *cross-repo* `@narrativeos/ui` source of truth still lives at `linchangWeb/packages/narrativeos-ui`, and Forge currently consumes its pinned v0.1.4 archive. We did not edit or silently fork that archive. If the sidebar is to be shared with the public plaza, promote the generic shell and common style tokens into the portal's shared package, publish a new verified archive, then migrate both consumers together. Keep app-specific navigation routes, content fetching and locale copy in their own apps.

A later component inventory should address the remaining NarAgent-specific previews, cards, modal wrappers and controls. Do not claim these have been deduplicated in phase 1.

## Verification checklist

- Run `node --test tests/practice_shared_navigation.test.cjs`.
- Run `npm ci` and `npm run build` from `forge_frontend_next`.
- Desktop: toggle expanded/collapsed; preserve existing resizable widths; check preview pane and header.
- Mobile: start with narrow rail, expand it, access account, create a new conversation and open a recent work.
- Check login, SSO/logout, browser back/forward, internal `basePath` routes, keyboard focus and reduced motion.
- Compare in browser with the public teacher resource plaza. Review release/deployment independently.
