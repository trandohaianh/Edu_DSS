# EduDSS — Live Demo Script

Format per step: **Click** (what to click) / **Say** (what to say while it loads/appears) /
**Point at** (what on screen to gesture to) / **Don't say** (dangerous phrase to avoid) /
**Fallback** (what to do if this step fails live).

---

## Step 0 — Setup (before the committee arrives)

- Start the app: `d:/KLTN/code/.venv/Scripts/python.exe -m streamlit run run_dss.py`
  (or `run_dss.py` via the configured launcher). **Never use a system-wide Python.**
- Confirm `EDUDSS_MODE` is `DEMO_SYNTHETIC` (default) so demo data paths are available.
- Pre-warm the AI Advisor / Learning Explainer tab once before presenting, to absorb the
  ~55–60s cold-start delay (`COLDSTART-001`) outside the live window.
- **Fallback:** if the app won't start live, have the screenshot set from
  `VISUAL_ACCEPTANCE_MATRIX.csv` (`reports/final_ui_functional_audit/` evidence files)
  ready as a backup walkthrough.

## Step 1 — Login & role switch

**Click:** Log in as a Student account.
**Say:** "This is the Student view — notice the sidebar only shows Student-appropriate
tabs; that's enforced both in navigation and at the function level underneath."
**Point at:** the sidebar tab list.
**Don't say:** "This is enterprise SSO" — it's a real but simplified password login.
**Fallback:** if login state is stale, use the browser's private/incognito window.

## Step 2 — Student Dashboard

**Click:** Home / Dashboard tab.
**Say:** "This shows this student's own risk prediction and progress — computed from the
current Production model, filtered to just this student's ID."
**Point at:** the risk-level card and any KPI row (call out the equal card heights —
`CARD-HEIGHT-001` was a real fix verified with `getBoundingClientRect()` measurements).
**Don't say:** "This updates in real time" — it recomputes per page load, not a live feed.
**Fallback:** if the model shows an empty state, explain: "This is the honest empty state
when no Production model exists yet — not a bug."

## Step 3 — ML Prediction (Classification or Regression)

**Click:** ML Hub / Du doan ML tab, run a prediction on the sample dataset.
**Say:** "This dataset is synthetic, generated for demo purposes — I'll be upfront that
no real institutional dataset is used here. Behind this prediction, four algorithms were
compared using GridSearchCV — I can give exact grid sizes if asked."
**Point at:** the model comparison table / metrics.
**Don't say:** "This is trained on real student records."
**Fallback:** if training is slow live, use an already-trained Production model instead of
retraining from scratch.

## Step 4 — SHAP Explanation

**Click:** the explanation/SHAP panel for a single prediction.
**Say:** "This shows which features contributed most to this specific prediction, using
Shapley values — it's telling us what the model weighted, not proving what causes the
outcome in reality."
**Don't say:** "This proves X causes Y."

## Step 5 — Clustering

**Click:** Phan cum / Clustering tab.
**Say:** "This is K-Means — unsupervised grouping by similarity, not a prediction of
outcomes. The number of clusters was chosen using elbow and silhouette analysis."
**Point at:** the cluster scatter plot (PCA-projected) and the silhouette score.
**Don't say:** "The clustering predicts who will fail."

## Step 6 — Diagnosis & Learning Plan

**Click:** AI Advisor → Learning Plan tab.
**Say:** "The diagnosis behind this plan is rule-based — explicit threshold logic, fully
traceable — not a black-box model. The plan structure itself is also rule-based; the
language model's only job is to phrase it naturally for the student."
**Don't say:** "The AI designed this plan."

## Step 7 — RAG / Learning Explainer (the centerpiece)

**Click:** AI Advisor → Learning Explainer, ask a question about previously-uploaded
lecture content.
**Say:** "Watch the citation that comes back — it's a real quote traced to the actual
uploaded document, not a generic answer. If I ask something with no matching content, it
should honestly say it found no relevant evidence rather than guessing."
**Point at:** the citation/source link in the response.
**Don't say:** "This never hallucinates" — say "there's a heuristic check, not a formal
guarantee."
**Fallback:** if the cold-start delay hits live (first access can take ~55–60s), say: "This
is a known one-time cold-start cost I've documented — the pre-warmed session I have ready
will show the fast path" and switch to the pre-warmed instance/tab.

## Step 8 — Admin: Model Registry

**Click:** switch to Admin, open Model Registry.
**Say:** "Models move through candidate, production, and archived states. Promotion is
Admin-gated only — training never auto-promotes, even though the system internally
tracks which candidate performed best."
**Don't say:** "The best model gets promoted automatically."

## Step 9 — Admin: Knowledge Base / Settings

**Click:** Quan ly tri thuc (Knowledge Base) tab.
**Say:** "Admin can upload and browse documents here. I'll be upfront that update and
delete aren't wired to the UI yet — that's a known, deliberately scoped-out gap, not an
oversight."
**Don't say:** "Full document management is supported."

## Step 10 — Closing the demo

**Say:** "That's the full loop — prediction, explanation, diagnosis, a grounded AI advisor,
and the governance layer around it — all covered by the 426-test suite I'll reference in
questions. Happy to go deeper into any part."
