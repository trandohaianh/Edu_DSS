"""EduDSS evaluation suite — one command, gated, with baselines and history.

    python evals/run_evals.py                      # all sections (~3-5 min on 2 CPUs)
    python evals/run_evals.py --skip-ml            # fast: RAG + safety only (seconds)
    python evals/run_evals.py --update-baseline    # after an intentional improvement

Sections
  ml      The app's OWN trainers (dss.core.trainers) fit on synthetic cohort seed 42 (2,000
          students) and are scored on an INDEPENDENT cohort seed 7 (1,000 students):
          grade-band classifier (accuracy, macro-F1, lift over a majority-class dummy),
          next-term score regressor (MAE, R² vs a mean dummy), at-risk screening built on the
          regressor (recall/precision for next-term score < 6.0), and the leakage guard
          (a copy of the target passed as a feature must be dropped).
  rag     Retrieval on the built-in knowledge base (19 documents) with the labelled benchmark
          dss.services.rag_evaluator.STANDARD_RAG_BENCHMARK_SET (23 queries): a lexical
          TF-IDF baseline always, plus the production embedding model when it can be loaded
          (sentence-transformers + Hugging Face access — CI has both, sandboxes may not).
  safety  Hand-written golden sets in evals/datasets: harmful-advice detector
          (llm_evaluator) recall / false-flag rate, and prompt-injection filter
          (prompt_security.sanitize_untrusted_text) block rate / benign alteration rate,
          English and Vietnamese attacks.

Gates live in evals/thresholds.json; regressions are checked against evals/baselines/<profile>.json.
Results: reports/evals/latest.json, latest.md, history.jsonl (+ $GITHUB_STEP_SUMMARY in CI).
All data is synthetic or hand-written: these numbers say the code works as designed, NOT how
accurate EduDSS would be on a real school's students.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

EVALS = Path(__file__).resolve().parent
APP = EVALS.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

# metric -> direction for regression checks
HIGHER = ["ml_clf_accuracy", "ml_clf_macro_f1", "ml_clf_lift_over_dummy", "ml_reg_r2", "ml_at_risk_recall",
          "ml_at_risk_precision", "rag_lexical_recall_at_5", "rag_lexical_mrr", "rag_semantic_recall_at_5",
          "rag_semantic_mrr", "rag_semantic_multilingual_recall_at_5", "rag_semantic_multilingual_mrr", "safety_harmful_recall", "injection_block_rate",
          "holdout_safety_harmful_recall", "holdout_injection_block_rate",
          "holdout2_safety_harmful_recall", "holdout2_injection_block_rate",
          "ml_real_start_auc", "ml_real_midterm_auc", "ml_real_start_recall", "ml_real_midterm_recall",
          "ml_real_start_precision", "ml_real_midterm_precision"]
LOWER = ["ml_reg_mae", "safety_false_flag_rate", "injection_benign_altered_rate",
         "holdout_safety_false_flag_rate", "holdout_injection_benign_altered_rate",
         "holdout2_safety_false_flag_rate", "holdout2_injection_benign_altered_rate",
         "ml_real_start_ece", "ml_real_midterm_ece", "ml_real_start_recall_gap_sex", "ml_real_midterm_recall_gap_sex",
         "ml_real_start_recall_gap_address", "ml_real_midterm_recall_gap_address"]
AT_RISK_THRESHOLD = 6.0
TARGETS = ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")


def _quiet():
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    os.environ.setdefault("EDUDSS_SKIP_DOTENV", "1")


# ------------------------------------------------------------------------------------ ML
def _best(results: dict, key: str, higher: bool = True) -> str:
    scored = {k: v[key] for k, v in results.items() if not k.startswith("__") and isinstance(v, dict) and key in v}
    return (max if higher else min)(scored, key=scored.get)


def eval_ml() -> dict:
    import numpy as np
    from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score

    from dss.core.data_helpers import generate_data
    from dss.core.trainers import ClassificationTrainer, RegressionTrainer

    train = generate_data(n_students=2000, random_state=42)
    test = generate_data(n_students=1000, random_state=7)
    features = [c for c in train.columns if c not in TARGETS]
    out: dict = {"ml_train_rows": len(train), "ml_test_rows": len(test)}

    clf = ClassificationTrainer()
    wanted = [m for m in ("Logistic Regression (Softmax)", "LightGBM Classifier") if m in clf.models] or list(clf.models)[:2]
    res, pipes, labels, used, *_ = clf.train_and_evaluate(train, features, "xep_loai", wanted, cv_folds=3, save_model=False)
    best = _best(res, "F1 Score (Macro)")
    pred = pipes[best].predict(test[used])
    if labels is not None and len(pred) and not isinstance(pred[0], str):
        pred = np.asarray(labels)[np.asarray(pred, dtype=int)]
    truth = test["xep_loai"].to_numpy()
    majority = train["xep_loai"].mode()[0]
    out.update({
        "ml_clf_model": best,
        "ml_clf_accuracy": round(accuracy_score(truth, pred), 4),
        "ml_clf_macro_f1": round(f1_score(truth, pred, average="macro", zero_division=0), 4),
        "ml_clf_dummy_accuracy": round(float((truth == majority).mean()), 4),
    })
    out["ml_clf_lift_over_dummy"] = round(out["ml_clf_accuracy"] - out["ml_clf_dummy_accuracy"], 4)

    reg = RegressionTrainer()
    wanted = [m for m in ("Linear Regression", "LightGBM Regressor") if m in reg.models] or list(reg.models)[:2]
    # final_score is a verbatim copy of the target in the generator: passing it on purpose
    # checks the trainer's leakage guard (computed on the training split only) drops it.
    r_res, r_pipes, _, r_used, *_ = reg.train_and_evaluate(train, features + ["final_score"], "diem_ky_sau",
                                                           wanted, cv_folds=3, save_model=False)
    best_r = _best(r_res, "R2 Score")
    y_true = test["diem_ky_sau"].to_numpy()
    y_pred = np.asarray(r_pipes[best_r].predict(test[r_used]), dtype=float)
    flagged, actual = y_pred < AT_RISK_THRESHOLD, y_true < AT_RISK_THRESHOLD
    tp = int((flagged & actual).sum())
    out.update({
        "ml_reg_model": best_r,
        "ml_reg_mae": round(mean_absolute_error(y_true, y_pred), 4),
        "ml_reg_r2": round(r2_score(y_true, y_pred), 4),
        "ml_reg_dummy_mae": round(float(np.abs(y_true - train["diem_ky_sau"].mean()).mean()), 4),
        "ml_at_risk_prevalence": round(float(actual.mean()), 4),
        "ml_at_risk_recall": round(tp / max(1, int(actual.sum())), 4),
        "ml_at_risk_precision": round(tp / max(1, int(flagged.sum())), 4),
        "ml_leakage_guard_ok": "final_score" not in r_used,
    })
    return out


# ------------------------------------------------------------------------------------ ML on REAL data
def _ece(y_true, prob, bins: int = 10) -> float:
    import numpy as np

    y_true, prob = np.asarray(y_true, dtype=float), np.asarray(prob, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (prob >= lo) & ((prob < hi) if hi < 1 else (prob <= hi))
        if mask.any():
            total += mask.mean() * abs(prob[mask].mean() - y_true[mask].mean())
    return float(total)


def _group_gap(y_true, y_pred, groups) -> dict:
    """Chênh lệch recall (bắt được HS có nguy cơ) và FPR giữa các nhóm: max - min."""
    import numpy as np

    y_true, y_pred, groups = map(np.asarray, (y_true, y_pred, groups))
    recalls, fprs = {}, {}
    for g in sorted(set(groups)):
        m = groups == g
        pos, neg = m & (y_true == 1), m & (y_true == 0)
        if pos.sum() >= 3:
            recalls[str(g)] = float(y_pred[pos].mean())
        if neg.sum() >= 3:
            fprs[str(g)] = float(y_pred[neg].mean())
    gap = lambda d: round(max(d.values()) - min(d.values()), 4) if len(d) >= 2 else None   # noqa: E731
    return {"recall_by_group": {k: round(v, 4) for k, v in recalls.items()}, "recall_gap": gap(recalls),
            "fpr_by_group": {k: round(v, 4) for k, v in fprs.items()}, "fpr_gap": gap(fprs)}


def eval_ml_real(seeds=(1, 2, 3, 4, 5), models=("Logistic Regression (Softmax)",), target_recall: float = 0.8) -> dict:
    """Trainer của app trên học sinh THẬT (UCI Student Performance, 649 HS): cảnh báo trượt (G3 < 10)."""
    import numpy as np
    import pandas as pd
    from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    from dss.core.trainers import ClassificationTrainer

    df = pd.read_csv(EVALS / "datasets" / "uci_student" / "student-por.csv", sep=";")
    df["at_risk"] = np.where(df["G3"] < 10, "Có nguy cơ", "Ổn")
    out: dict = {"ml_real_rows": len(df), "ml_real_prevalence": round(float((df["G3"] < 10).mean()), 4)}
    scenarios = {"start": [c for c in df.columns if c not in ("G1", "G2", "G3", "at_risk")],
                 "midterm": [c for c in df.columns if c not in ("G2", "G3", "at_risk")]}
    rules = {"start": lambda d: (d["failures"] > 0).astype(int), "midterm": lambda d: (d["G1"] < 10).astype(int)}
    for name, feats in scenarios.items():
        rows = []
        for seed in seeds:
            train, test = train_test_split(df, test_size=0.25, random_state=seed, stratify=df["at_risk"])
            clf = ClassificationTrainer()
            # Mặc định chỉ Logistic Regression: GridSearch của LightGBM trên 2 lõi CI mất > 10 phút cho
            # 10 lần huấn luyện. Muốn so mô hình cây: eval_ml_real(models=(..., "LightGBM Classifier")).
            wanted = [m for m in models if m in clf.models]
            res, pipes, labels, used, *_ = clf.train_and_evaluate(train, feats, "at_risk", wanted, cv_folds=3,
                                                                   save_model=False)
            best = _best(res, "F1 Score (Macro)")
            pipe = pipes[best]
            classes = list(getattr(pipe, "classes_", []))
            proba = pipe.predict_proba(test[used])
            if classes and not isinstance(classes[0], str):
                classes = [labels[int(c)] for c in classes]
            p_risk = proba[:, classes.index("Có nguy cơ")] if classes else proba[:, 0]
            y = (test["G3"] < 10).astype(int).to_numpy()
            pred = (p_risk >= 0.5).astype(int)
            # Ngưỡng cảnh báo: chọn trên xác suất out-of-fold của TẬP TRAIN (không nhìn test) sao cho
            # bắt được >= target_recall học sinh có nguy cơ. Ngưỡng 0,5 tối ưu accuracy, không tối ưu
            # việc không bỏ sót em nào — sai mục tiêu với hệ cảnh báo sớm.
            from sklearn.base import clone
            from sklearn.model_selection import StratifiedKFold, cross_val_predict

            y_train_lbl = train["at_risk"].to_numpy()
            if classes and isinstance(getattr(pipe, "classes_", ["x"])[0], str):
                y_fit = y_train_lbl
            else:
                y_fit = np.array([list(labels).index(v) for v in y_train_lbl])
            oof = cross_val_predict(clone(pipe), train[used], y_fit, method="predict_proba",
                                    cv=StratifiedKFold(5, shuffle=True, random_state=seed))[:, classes.index("Có nguy cơ")]
            y_tr = (train["G3"] < 10).astype(int).to_numpy()
            pos = np.sort(oof[y_tr == 1])
            thr = float(pos[int(np.floor((1 - target_recall) * len(pos)))]) if len(pos) else 0.5
            pred_t = (p_risk >= thr).astype(int)
            rule = rules[name](test).to_numpy()
            rows.append({
                "auc": roc_auc_score(y, p_risk), "recall": recall_score(y, pred, zero_division=0),
                "precision": precision_score(y, pred, zero_division=0), "brier": brier_score_loss(y, p_risk),
                "thr": thr, "recall_t": recall_score(y, pred_t, zero_division=0),
                "precision_t": precision_score(y, pred_t, zero_division=0),
                "alert_rate_t": float(pred_t.mean()), "rule_alert_rate": float(rule.mean()),
                "ece": _ece(y, p_risk), "rule_recall": recall_score(y, rule, zero_division=0),
                "rule_precision": precision_score(y, rule, zero_division=0),
                "sex": _group_gap(y, pred_t, test["sex"]), "address": _group_gap(y, pred_t, test["address"]),
                "model": best,
            })
        mean = lambda key: round(float(np.mean([r[key] for r in rows])), 4)   # noqa: E731
        std = lambda key: round(float(np.std([r[key] for r in rows])), 4)     # noqa: E731
        gaps = lambda attr, key: round(float(np.mean([r[attr][key] for r in rows if r[attr][key] is not None])), 4)  # noqa: E731
        p = f"ml_real_{name}_"
        out.update({p + "auc": mean("auc"), p + "auc_std": std("auc"), p + "recall_at_0_5": mean("recall"),
                    p + "precision_at_0_5": mean("precision"), p + "brier": mean("brier"), p + "ece": mean("ece"),
                    p + "threshold": mean("thr"), p + "recall": mean("recall_t"), p + "recall_std": std("recall_t"),
                    p + "precision": mean("precision_t"), p + "alert_rate": mean("alert_rate_t"),
                    p + "rule_alert_rate": mean("rule_alert_rate"),
                    p + "rule_recall": mean("rule_recall"), p + "rule_precision": mean("rule_precision"),
                    p + "recall_gap_sex": gaps("sex", "recall_gap"), p + "recall_gap_address": gaps("address", "recall_gap"),
                    p + "fpr_gap_sex": gaps("sex", "fpr_gap"), p + "fpr_gap_address": gaps("address", "fpr_gap"),
                    p + "models": sorted({r["model"] for r in rows})})
    return out


# ------------------------------------------------------------------------------------ RAG
def _rank_metrics(retrieve, cases, k: int = 5) -> dict:
    from dss.services import rag_evaluator

    result = rag_evaluator.evaluate_retrieval_pipeline(retrieve, test_cases=cases, k=k)
    s = result["summary"]
    misses = [d["query_id"] for d in result["details"] if not d["hits"]]
    return {"recall": s["mean_recall_at_k"], "mrr": s["mrr"], "ndcg": s["mean_ndcg_at_k"],
            "latency_ms": s["avg_latency_ms"], "misses": misses}


def eval_rag() -> dict:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    from dss.core.models import MultiAIProvider
    from dss.services import rag_evaluator

    provider = MultiAIProvider()
    docs = provider.knowledge_base["documents"]
    ids = [d["id"] for d in docs]
    texts = [f"{d['title']} {d['content']} {' '.join(d.get('tags', []))}" for d in docs]
    cases = rag_evaluator.STANDARD_RAG_BENCHMARK_SET
    out: dict = {"rag_documents": len(docs), "rag_queries": len(cases)}

    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
    matrix = vec.fit_transform(texts)

    def lexical(query, k):
        scores = (matrix @ vec.transform([query]).T).toarray().ravel()
        return [{"id": ids[i]} for i in np.argsort(-scores)[:k]]

    lex = _rank_metrics(lexical, cases)
    out.update({"rag_lexical_recall_at_5": lex["recall"], "rag_lexical_mrr": lex["mrr"],
                "rag_lexical_ndcg_at_5": lex["ndcg"], "rag_lexical_misses": lex["misses"]})

    from dss.core.release import EMBEDDING_MODEL, MULTILINGUAL_EMBEDDING_MODEL

    # Đo cả mô hình đang triển khai và mô hình đa ngôn ngữ (ứng viên thay thế cho tiếng Việt).
    for prefix, model in (("rag_semantic_", EMBEDDING_MODEL), ("rag_semantic_multilingual_", MULTILINGUAL_EMBEDDING_MODEL)):
        if prefix != "rag_semantic_" and model == EMBEDDING_MODEL:
            continue
        try:
            doc_emb = {}
            for doc_id, text in zip(ids, texts):
                emb = provider.get_embedding(text, embedding_model_name=model)
                if emb is None:
                    raise RuntimeError("embedding model unavailable")
                doc_emb[doc_id] = np.asarray(emb, dtype=float)

            def semantic(query, k, model=model, doc_emb=doc_emb):
                q = np.asarray(provider.get_embedding(query, embedding_model_name=model), dtype=float)
                scored = sorted(doc_emb, key=lambda d: -float(q @ doc_emb[d] / (np.linalg.norm(q) * np.linalg.norm(doc_emb[d]) + 1e-12)))
                return [{"id": d} for d in scored[:k]]

            sem = _rank_metrics(semantic, cases)
            out.update({prefix + "available": True, prefix + "model": model,
                        prefix + "recall_at_5": sem["recall"], prefix + "mrr": sem["mrr"],
                        prefix + "ndcg_at_5": sem["ndcg"], prefix + "latency_ms": sem["latency_ms"],
                        prefix + "misses": sem["misses"]})
        except Exception as exc:
            out.update({prefix + "available": False, prefix + "skip_reason": type(exc).__name__})
    return out


# ------------------------------------------------------------------------------------ safety
def eval_safety() -> dict:
    out = _safety_on("advisor_safety_v1.json", "prompt_injection_v1.json", "")
    # Holdout sets were written AFTER the filters were tuned on v1 and are never used for tuning:
    # they measure how far the keyword filters generalise (reported, gated loosely).
    out.update(_safety_on("advisor_safety_holdout_v1.json", "prompt_injection_holdout_v1.json", "holdout_"))
    # v2 được viết TRƯỚC khi huấn luyện bộ phân loại học được (dss/services/safety_classifier.py).
    out.update(_safety_on("advisor_safety_holdout_v2.json", "prompt_injection_holdout_v2.json", "holdout2_"))
    from dss.services.safety_classifier import thresholds
    out["safety_classifier_thresholds"] = thresholds()
    return out


def _safety_on(advice_file: str, injection_file: str, prefix: str) -> dict:
    from dss.services.llm_evaluator import detect_harmful_or_unsupported_advice
    from dss.services.prompt_security import sanitize_untrusted_text

    advice = json.loads((EVALS / "datasets" / advice_file).read_text(encoding="utf-8"))["cases"]
    harmful = [c for c in advice if c["label"] == "harmful"]
    safe = [c for c in advice if c["label"] == "safe"]
    missed = [c["id"] for c in harmful if not detect_harmful_or_unsupported_advice(c["text"])[0]]
    false_flags = [c["id"] for c in safe if detect_harmful_or_unsupported_advice(c["text"])[0]]

    inj = json.loads((EVALS / "datasets" / injection_file).read_text(encoding="utf-8"))["cases"]
    attacks = [c for c in inj if c["label"] == "attack"]
    benign = [c for c in inj if c["label"] == "benign"]
    # "Blocked" = the filter changed the text (replaced an override phrase or escaped a fake
    # boundary tag); a benign input must come back unchanged.
    passed = [c["id"] for c in attacks if sanitize_untrusted_text(c["text"]) == c["text"].strip()]
    altered = [c["id"] for c in benign if sanitize_untrusted_text(c["text"]) != c["text"].strip()]
    result = {
        "safety_harmful_cases": len(harmful), "safety_safe_cases": len(safe),
        "safety_harmful_recall": round(1 - len(missed) / len(harmful), 4),
        "safety_false_flag_rate": round(len(false_flags) / len(safe), 4),
        "safety_missed": missed, "safety_false_flags": false_flags,
        "injection_attacks": len(attacks), "injection_benign": len(benign),
        "injection_block_rate": round(1 - len(passed) / len(attacks), 4),
        "injection_benign_altered_rate": round(len(altered) / len(benign), 4),
        "injection_passed": passed, "injection_benign_altered": altered,
    }
    return {prefix + k: v for k, v in result.items()}


# ------------------------------------------------------------------------------------ gates
def gates(metrics: dict, thresholds: dict) -> list[str]:
    failures = []
    for name, floor in thresholds.get("min", {}).items():
        value = metrics.get(name)
        if value is not None and value < floor:
            failures.append(f"{name} = {value} < {floor}")
    for name, ceiling in thresholds.get("max", {}).items():
        value = metrics.get(name)
        if value is not None and value > ceiling:
            failures.append(f"{name} = {value} > {ceiling}")
    for name in thresholds.get("must_be_true", []):
        if name in metrics and metrics[name] is not True:
            failures.append(f"{name} is not true")
    return failures


def regressions(metrics: dict, baseline: dict, tolerance: float) -> tuple[list[str], dict]:
    found, deltas = [], {}
    for name in HIGHER + LOWER:
        if not isinstance(metrics.get(name), (int, float)) or not isinstance(baseline.get(name), (int, float)):
            continue
        delta = round(metrics[name] - baseline[name], 4)
        deltas[name] = delta
        worse = -delta if name in HIGHER else delta
        if worse > tolerance:
            found.append(f"{name}: {baseline[name]} -> {metrics[name]}")
    return found, deltas


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=APP, capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except Exception:
        return None


def _markdown(report: dict) -> str:
    m = report["metrics"]
    def row(label, key, fmt="{:.4f}"):
        value = m.get(key)
        shown = "—" if value is None else (fmt.format(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value))
        delta = report["deltas"].get(key)
        return f"| {label} | {shown} | {'' if delta is None else f'{delta:+.4f}'} |"
    lines = [f"# EduDSS eval — {report['status'].upper()}", "",
             f"Profile `{report['profile']}` · commit `{report.get('git_sha')}` · {report['finished_at']} · {report['duration_s']}s", "",
             "| Metric | Value | Δ vs baseline |", "|---|---|---|"]
    for label, key in [("Grade band accuracy (independent cohort)", "ml_clf_accuracy"), ("Grade band macro-F1", "ml_clf_macro_f1"),
                       ("Majority-class dummy accuracy", "ml_clf_dummy_accuracy"), ("Next-term score MAE", "ml_reg_mae"),
                       ("Next-term score R²", "ml_reg_r2"), ("At-risk (<6.0) recall", "ml_at_risk_recall"),
                       ("At-risk precision", "ml_at_risk_precision"), ("Leakage guard drops target copy", "ml_leakage_guard_ok"),
                       ("RAG lexical recall@5", "rag_lexical_recall_at_5"), ("RAG lexical MRR", "rag_lexical_mrr"),
                       ("RAG semantic recall@5", "rag_semantic_recall_at_5"), ("RAG semantic MRR", "rag_semantic_mrr"),
                       ("Harmful advice recall", "safety_harmful_recall"), ("Safe advice false-flag rate", "safety_false_flag_rate"),
                       ("Prompt-injection block rate", "injection_block_rate"),
                       ("Benign input altered rate", "injection_benign_altered_rate"),
                       ("HOLDOUT harmful advice recall", "holdout_safety_harmful_recall"),
                       ("HOLDOUT safe advice false-flag rate", "holdout_safety_false_flag_rate"),
                       ("HOLDOUT prompt-injection block rate", "holdout_injection_block_rate"),
                       ("HOLDOUT benign input altered rate", "holdout_injection_benign_altered_rate"),
                       ("HOLDOUT v2 harmful advice recall", "holdout2_safety_harmful_recall"),
                       ("HOLDOUT v2 safe advice false-flag rate", "holdout2_safety_false_flag_rate"),
                       ("HOLDOUT v2 prompt-injection block rate", "holdout2_injection_block_rate"),
                       ("HOLDOUT v2 benign input altered rate", "holdout2_injection_benign_altered_rate"),
                       ("RAG multilingual semantic recall@5", "rag_semantic_multilingual_recall_at_5"),
                       ("REAL students (UCI, 649) start-of-term AUC", "ml_real_start_auc"),
                       ("REAL start-of-term recall @ train-OOF threshold", "ml_real_start_recall"),
                       ("REAL start-of-term precision", "ml_real_start_precision"),
                       ("REAL rule 'failures>0' recall", "ml_real_start_rule_recall"), ("REAL rule 'failures>0' precision", "ml_real_start_rule_precision"),
                       ("REAL midterm (with G1) AUC", "ml_real_midterm_auc"),
                       ("REAL midterm recall", "ml_real_midterm_recall"),
                       ("REAL midterm precision", "ml_real_midterm_precision"),
                       ("REAL rule 'G1<10' recall", "ml_real_midterm_rule_recall"),
                       ("REAL rule 'G1<10' precision", "ml_real_midterm_rule_precision"),
                       ("REAL midterm ECE (calibration)", "ml_real_midterm_ece"),
                       ("REAL midterm recall gap by sex", "ml_real_midterm_recall_gap_sex"),
                       ("REAL midterm recall gap urban/rural", "ml_real_midterm_recall_gap_address")]:
        if key in m:
            lines.append(row(label, key))
    if report["failures"]:
        lines += ["", "## Failures", *[f"- {f}" for f in report["failures"]]]
    if m.get("rag_semantic_available") is False:
        lines += ["", f"_Semantic RAG skipped: {m.get('rag_semantic_skip_reason')} (no embedding model here)._"]
    lines += ["", "_Synthetic cohorts and hand-written golden sets: these numbers show the code works as designed, "
                  "not accuracy on a real school's students._"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ml", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--output-dir", default=str(APP / "reports" / "evals"))
    args = parser.parse_args(argv)
    _quiet()
    profile = "fast" if args.skip_ml else "full"
    started = time.time()
    metrics: dict = {}
    sections = [("rag", eval_rag), ("safety", eval_safety)] + ([] if args.skip_ml else [("ml", eval_ml), ("ml_real", eval_ml_real)])
    for name, fn in sections:
        t0 = time.time()
        print(f"[eval] {name}…", flush=True)
        metrics.update(fn())
        metrics[f"{name}_seconds"] = round(time.time() - t0, 1)
    thresholds = json.loads((EVALS / "thresholds.json").read_text(encoding="utf-8"))
    failures = gates(metrics, thresholds)
    baseline_path = EVALS / "baselines" / f"{profile}.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    regs, deltas = regressions(metrics, baseline, thresholds.get("regression_tolerance", 0.03))
    failures += [f"regression {r}" for r in regs]
    report = {"status": "pass" if not failures else "fail", "profile": profile, "git_sha": _git_sha(),
              "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "duration_s": round(time.time() - started, 1), "metrics": metrics, "deltas": deltas,
              "failures": failures}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = _markdown(report)
    (out / "latest.md").write_text(md, encoding="utf-8")
    with open(out / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({k: report[k] for k in ("status", "profile", "git_sha", "finished_at")} |
                           {k: v for k, v in metrics.items() if isinstance(v, (int, float, bool))}, ensure_ascii=False) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in metrics.items() if k in HIGHER + LOWER}
        baseline_path.write_text(json.dumps(keep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[eval] baseline written: {baseline_path}")
    print(md)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
