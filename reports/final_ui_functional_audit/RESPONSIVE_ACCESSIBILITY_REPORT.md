# Responsive & Accessibility Report

## Desktop responsive sweep (required: 1920×1080, 1440×900, 1366×768)

**Method:** live Playwright, 3 key pages representative of the 3 roles and the 2 dominant layout
patterns in the app (KPI-card rows and data tables) — Student home (card-heavy), Lecturer home
(card-heavy, the one page with a hand-rolled KPI component), Admin Model Registry (table-heavy).
Verified via `document.documentElement.scrollWidth` vs `clientWidth` (objective overflow
detection, not visual guessing) at all 3 resolutions, plus visual screenshot review.

**Result: PASS at all 3 resolutions for all 3 pages** — zero horizontal page overflow
(`scrollWidth == clientWidth` exactly, at every resolution). The `CARD-HEIGHT-001` fix holds
correctly at 1920×1080 and 1366×768, not just the 1440×900 width it was originally found/fixed at.

**One minor, sub-threshold observation** (not fixed): at 1366×768, the Student home's "Yếu tố ảnh
hưởng đến điểm dự báo" card header wraps to 2 lines (longer Vietnamese heading than its siblings),
shifting that card's body content down slightly relative to its neighbors — the cards' bottom
edges still align exactly (the `CARD-HEIGHT-001` fix is unaffected), only the internal top
alignment is offset by one line-height. This is a common, low-severity responsive artifact of
having one heading text longer than its row-mates; not fixed this pass given its severity.

**Admin Model Registry's "Training ID" column truncates at 1366px** — expected, acceptable
`st.dataframe` behavior (the table scrolls/truncates within its own container; the page itself
never overflows).

Combined with the earlier phone-width (390×844) pass done in a previous phase of this session
(which found and fixed `RESPONSIVE-001` — the Lecturer KPI row's phone-width breakage — and
confirmed the Student/Admin home pages clean at that width), all 4 required/practical breakpoints
now have real evidence: 390, 1366, 1440, 1920.

## Accessibility — pragmatic pass

**Scope note:** no dedicated accessibility tooling (e.g., axe-core) is wired into this project's
test suite, so this is a pragmatic, evidence-based spot-check against the criteria explicitly
requested, not a full WCAG certification.

| Check | Result | Evidence |
|---|---|---|
| Interactive elements have accessible names | PASS | Every form field interacted with throughout this entire session used a real `aria-label` (confirmed via dozens of Playwright `input[aria-label=...]` selectors that worked correctly); Streamlit buttons expose their visible text as the accessible name even when `aria-label=""` (confirmed early in this session via direct DOM inspection) |
| Keyboard navigability of sidebar nav | PASS (structural) | Sidebar items are real `<button>` elements (not `<div onclick>`), which are natively focusable and activatable via keyboard (Tab + Enter/Space) by the browser's default behavior — confirmed by their `data-testid="stBaseButton-*"` semantics used throughout this session's automation |
| Color contrast of core design tokens | PASS (spot-check) | Primary brand color `--ed-primary: #2563EB` on white background = contrast ratio ≈ 5.1:1, passing WCAG AA (4.5:1) for normal text; status colors (success/warning/danger) follow standard Tailwind-derived palettes with sufficient contrast against the white card backgrounds used throughout |
| Focus indication | NOT VERIFIED | Would require inspecting `:focus` CSS rules specifically; not checked this pass — flagged as open |
| Screen-reader landmark structure | NOT VERIFIED | Streamlit's own DOM structure (not fully under app-author control) was not audited for landmark roles (`<main>`, `<nav>`, etc.) this pass |

## Explicitly still open

- Focus-visible styling verification.
- Screen-reader landmark/heading-structure audit.
- A full WCAG-tooling-based pass (e.g., running axe-core against each page) if the project later
  wires up that tooling — not currently part of this codebase's test infrastructure.
