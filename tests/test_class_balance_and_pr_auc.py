"""Kiểm thử ba sửa đổi quanh cân bằng lớp và chỉ số chọn mô hình.

Bối cảnh: lớp thiểu số trong bộ dữ liệu của dự án có thể chỉ còn vài mẫu. Ở cỡ đó:

1. SMOTE/ADASYN KHÔNG chạy được (cần >= 2 mẫu cùng lớp trong mỗi fold train để nội
   suy). Trước đây mã chỉ ghi log rồi chạy tiếp, nên kết quả vẫn được báo cáo như thể
   đã cân bằng lớp — đó là thông tin sai. Giờ kết quả phải mang cờ phân biệt YÊU CẦU
   và THỰC TẾ.
2. class_weight='balanced' là phương án dùng được ở cỡ đó vì nó không sinh mẫu.
3. F1 đo tại MỘT ngưỡng nên dịch rất mạnh khi lớp hiếm chỉ vài mẫu; PR-AUC lấy trung
   bình trên toàn dải ngưỡng nên đo đúng khả năng xếp hạng — thứ sản phẩm thực sự dùng.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from dss.core.trainers import apply_class_weight_balanced, pr_auc_macro


class TestApplyClassWeight:
    def test_dat_duoc_class_weight_cho_estimator_ho_tro(self):
        model, applied = apply_class_weight_balanced(LogisticRegression(random_state=42))
        assert applied is True
        assert model.get_params()["class_weight"] == "balanced"

    def test_khong_sua_doi_model_goc(self):
        goc = LogisticRegression(random_state=42)
        model, _ = apply_class_weight_balanced(goc)
        assert goc.get_params()["class_weight"] is None, "phải trả về bản sao, không sửa tại chỗ"
        assert model is not goc

    def test_bao_cao_that_bai_khi_estimator_khong_ho_tro(self):
        class KhongHoTro:
            def get_params(self, deep=True):
                return {"n_estimators": 10}

        model = KhongHoTro()
        tra_ve, applied = apply_class_weight_balanced(model)
        assert applied is False, "phải trả cờ False để nơi gọi ghi log, không im lặng bỏ qua"
        assert tra_ve is model

    def test_giu_nguyen_cac_tham_so_khac(self):
        model, _ = apply_class_weight_balanced(RandomForestClassifier(n_estimators=37, max_depth=4, random_state=7))
        p = model.get_params()
        assert p["n_estimators"] == 37 and p["max_depth"] == 4 and p["random_state"] == 7


class TestPrAucMacro:
    def test_nhi_phan_xep_hang_hoan_hao_cho_diem_toi_da(self):
        y = np.array([0, 0, 0, 1, 1])
        proba = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3], [0.2, 0.8], [0.1, 0.9]])
        assert pr_auc_macro(y, proba, classes=[0, 1]) == pytest.approx(1.0)

    def test_da_lop_tra_ve_gia_tri_trong_khoang_0_1(self):
        rng = np.random.RandomState(0)
        y = np.array([0] * 20 + [1] * 20 + [2] * 20)
        proba = rng.dirichlet(np.ones(3), size=60)
        val = pr_auc_macro(y, proba, classes=[0, 1, 2])
        assert val is not None and 0.0 <= val <= 1.0

    def test_tra_ve_none_khi_khong_co_xac_suat(self):
        assert pr_auc_macro(np.array([0, 1]), None, classes=[0, 1]) is None

    def test_tra_ve_none_khi_tap_test_chi_co_mot_lop(self):
        assert pr_auc_macro(np.array([1, 1, 1]), np.array([[0.1, 0.9]] * 3), classes=[1]) is None

    def test_khong_nem_loi_khi_so_cot_xac_suat_lech_so_lop(self):
        y = np.array([0, 1, 2, 0, 1, 2])
        proba = np.array([[0.5, 0.5]] * 6)  # 2 cột nhưng 3 lớp
        assert pr_auc_macro(y, proba, classes=[0, 1, 2]) is None

    def test_pr_auc_on_dinh_hon_f1_khi_lop_hiem_rat_it_mau(self):
        """Đổi đúng MỘT mẫu: F1 nhảy bậc, PR-AUC dịch nhẹ.

        Đây là lý do kỹ thuật để báo cáo PR-AUC bên cạnh F1-macro.
        """
        from sklearn.metrics import f1_score

        y = np.array([0] * 8 + [1, 1])  # lớp hiếm: 2 trên 10
        # Mô hình A: bắt được 1 trong 2 mẫu hiếm.  Mô hình B: bắt được cả 2.
        pred_a = np.array([0] * 8 + [1, 0])
        pred_b = np.array([0] * 8 + [1, 1])
        f1_a = f1_score(y, pred_a, average="macro", zero_division=0)
        f1_b = f1_score(y, pred_b, average="macro", zero_division=0)

        proba_a = np.array([[0.9, 0.1]] * 8 + [[0.2, 0.8], [0.55, 0.45]])
        proba_b = np.array([[0.9, 0.1]] * 8 + [[0.2, 0.8], [0.45, 0.55]])
        ap_a = pr_auc_macro(y, proba_a, classes=[0, 1])
        ap_b = pr_auc_macro(y, proba_b, classes=[0, 1])

        assert f1_b - f1_a > 0.15, "một mẫu làm F1-macro nhảy rất mạnh"
        assert abs(ap_b - ap_a) < 0.05, "PR-AUC gần như không đổi vì thứ tự xếp hạng không đổi"
