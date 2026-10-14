# EduDSS — 5-Minute Defense Script

Read time target: ~5 minutes at a natural pace. Say it, don't read it verbatim off a slide.

---

**[0:00–0:45] Problem & goal**

"University students often don't get individualized academic support until it's too
late — after a bad midterm, or a failed course. My thesis, EduDSS, is a Decision Support
System that gives Students, Lecturers, and Admins three different, role-appropriate views
into academic risk: prediction, diagnosis, and a concrete learning plan — not just a
dashboard of numbers."

**[0:45–1:45] Architecture in one breath**

"EduDSS is a single Streamlit application with three roles, each gated by a two-layer
access-control system — navigation-level and function-level. Underneath, there's a real
machine learning layer with four classification algorithms and four regression
algorithms, each properly cross-validated with GridSearchCV and protected against data
leakage by splitting the data before any preprocessing happens. There's also a K-Means
clustering module for peer grouping, and a rule-based Diagnosis Engine that flags specific,
explainable causes of academic risk — not a black box."

**[1:45–3:00] The AI layer**

"On top of that sits an AI Advisor with Retrieval-Augmented Generation — RAG. When a
student or lecturer uploads course material, it's chunked, embedded, and stored in a
vector index. When someone asks a question, the system retrieves the most relevant
chunks, checks they clear a confidence threshold, and only then asks the language model
to answer — grounded in a real citation back to the source document. If nothing relevant
is found, it says so honestly instead of making something up. This closed retrieval loop
is one of the things I verified live, end to end, with a real citation traced back to an
actual uploaded file."

**[3:00–4:00] What's genuinely done vs. honestly not**

"Everything I just described — prediction, diagnosis, clustering, RAG, citations, the
Model Registry's promotion workflow — is real, implemented, and covered by 426 passing
tests, including 23 real-browser end-to-end tests. What I want to be upfront about:
there's no live connection to an external LMS or CMS platform yet — that layer is
architecture-ready but not wired to a real system. And a PostgreSQL-backed vector store
exists as schema and connection code, but its actual read/write methods are stubs — the
system currently runs on a simpler file-based vector store instead."

**[4:00–5:00] Closing**

"So EduDSS is a working, tested prototype that demonstrates the full decision-support
pipeline — from raw academic data to an explainable, cited, role-appropriate
recommendation — built on genuinely leak-safe ML and a real retrieval-grounded AI layer,
with clearly documented boundaries around what would still need to happen before a real
institutional deployment. I'm happy to go deeper into any part of this — the ML pipeline,
the RAG architecture, or the test methodology."

---

**If asked to cut to 3 minutes:** keep 0:00–1:45 and 4:00–5:00 only; drop the AI-layer
paragraph to one sentence: "There's also a RAG-grounded AI advisor that only answers from
retrieved, cited course material and honestly declines when it finds nothing relevant."
