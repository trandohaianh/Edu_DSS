import pandas as pd

from dss.services import clustering_service


def test_compute_strengths_weaknesses_never_empty_when_features_exist():
    # Case: all features within +/- 10% (e.g. +6% and +9.1% like in user screenshot)
    group_avg = pd.Series({"diem_tong_ket": 7.5, "gpa_ky_truoc": 7.8})
    overall_avg = pd.Series({"diem_tong_ket": 7.1, "gpa_ky_truoc": 7.15})

    strengths, weaknesses = clustering_service.compute_strengths_weaknesses(group_avg, overall_avg)
    assert len(strengths) > 0, "Phải xác định được thế mạnh tương đối khi nằm trong ngưỡng cân bằng"
    assert len(weaknesses) > 0, "Phải xác định được trọng tâm bứt phá khi nằm trong ngưỡng cân bằng"
    assert strengths[0] == "gpa_ky_truoc"
    assert weaknesses[0] == "diem_tong_ket"


def test_compute_intervention_plan_structure():
    diff_pct = pd.Series({"diem_tong_ket": 6.0, "gpa_ky_truoc": 9.1})
    selected_cols = ["diem_tong_ket", "gpa_ky_truoc"]

    plan_df = clustering_service.compute_intervention_plan(diff_pct, selected_cols)
    assert "Chỉ số" in plan_df.columns
    assert "Chênh lệch so với nhóm (%)" in plan_df.columns
    assert "Mức ưu tiên" in plan_df.columns
    assert "Hành động gợi ý" in plan_df.columns
    assert len(plan_df) == 2


def test_find_reference_cluster_with_and_without_weaknesses():
    cluster_means = pd.DataFrame({"diem_tong_ket": [6.5, 8.5, 7.5], "gpa_ky_truoc": [6.8, 8.8, 7.8]}, index=[0, 1, 2])

    # When cluster 0 is weak in both features, reference should be cluster 1
    ref = clustering_service.find_reference_cluster(cluster_means, 0, ["diem_tong_ket", "gpa_ky_truoc"])
    assert ref == 1

    # When no weaknesses provided, returns None
    ref_none = clustering_service.find_reference_cluster(cluster_means, 1, [])
    assert ref_none is None
