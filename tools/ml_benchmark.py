import sys, warnings, logging
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
sys.path.insert(0, ".")
from dss.core.data_helpers import generate_data
from dss.core.trainers import ClassificationTrainer, RegressionTrainer

df = generate_data()
print(df["xep_loai"].value_counts().to_dict())
feats = [c for c in df.columns if c not in ("student_id", "diem_ky_sau", "xep_loai", "final_score", "grade")]

clf = ClassificationTrainer()
res, pipes, labels, used, *_ = clf.train_and_evaluate(df, feats, "xep_loai", list(clf.models), cv_folds=5, save_model=False)
print("features used:", used)
for k, v in res.items():
    if k.startswith("__"): print(k, v); continue
    print(f"{k:32s} acc={v['Accuracy']:.4f} f1m={v['F1 Score (Macro)']:.4f} f1w={v['F1 Score (Weighted)']:.4f} train={v['Accuracy (Train)']:.4f}")

reg = RegressionTrainer()
r = reg.train_and_evaluate(df, feats, "diem_ky_sau", list(reg.models), cv_folds=5, save_model=False)
for k, v in r[0].items():
    if k.startswith("__"): print(k, v); continue
    print(f"{k:32s} RMSE={v['RMSE']:.4f} MAE={v['MAE']:.4f} R2={v['R2 Score']:.4f}")
