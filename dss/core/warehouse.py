"""Data warehouse and vector store."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

from dss.config import JOBLIB_AVAILABLE
from dss.core.data_root import get_data_root
from dss.core.logging_config import get_logger
from dss.core.persistence_config import is_postgres_enabled

_logger = get_logger(__name__)


def _current_organization_id() -> int:
    """Single-tenant deployment default: the whole running app instance
    serves ONE organization, identified by EDUDSS_ORGANIZATION_ID. No
    multi-tenant runtime context (e.g. a logged-in admin's own org) exists
    anywhere in the app today — that is Phase 5's job, not Phase 1B's."""
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        raise RuntimeError(
            "EDUDSS_ORGANIZATION_ID is required when a PostgreSQL-backed store is enabled "
            "(EDUDSS_PREDICTIONS_STORE/EDUDSS_CONSULTATIONS_STORE=postgres)."
        )
    return int(raw)


# ------------------------------------------------------------------ ký artifact (audit 17/11/2026)
# Trước đây mã băm SHA-256 nằm ngay trong metadata cạnh artifact, và ``model_path`` tuyệt đối trong metadata được
# đưa thẳng vào ``joblib.load``: ai ghi được thư mục dữ liệu là thay được cả artifact lẫn mã băm, hoặc trỏ tới một
# tệp pickle bất kỳ trên máy (joblib.load = thực thi mã). Nay:
# - chỉ tải ``<models>/<training_id>.joblib`` (training_id phải là định danh an toàn), bỏ qua ``model_path``;
# - metadata mang ``model_hmac`` = HMAC-SHA256(khoá, training_id + sha256) với khoá KHÔNG nằm trong thư mục dữ
#   liệu ở production (``EDUDSS_ARTIFACT_SIGNING_KEY``, hoặc dẫn xuất từ ``EDUDSS_PSEUDONYM_KEY`` bắt buộc ở
#   production), giống cách engine ký artifact;
# - artifact cũ chưa ký: ngoài production vẫn tải (kiểm SHA-256 như trước, ghi cảnh báo); ở production từ chối,
#   ký lại một lần bằng ``DataWarehouse().sign_legacy_models()`` sau khi đã kiểm chứng thư mục mô hình.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _artifact_key() -> bytes:
    raw = os.environ.get("EDUDSS_ARTIFACT_SIGNING_KEY", "")
    if len(raw.strip().encode("utf-8")) >= 32:
        return raw.strip().encode("utf-8")
    from dss.security.pseudonymization import _master_key

    return hmac.new(_master_key(), b"edudss-artifact-signing-v1", hashlib.sha256).digest()


def _artifact_tag(training_id: str, sha256_hex: str) -> str:
    return hmac.new(_artifact_key(), f"{training_id}:{sha256_hex}".encode(), hashlib.sha256).hexdigest()


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class DataWarehouse:
    """
    Class để quản lý việc lưu trữ và truy xuất dữ liệu, mô hình, và lịch sử làm việc.

    Kho dữ liệu chứa:
    - Dữ liệu thô đầu vào (raw_data): Dữ liệu gốc từ file upload
    - Dữ liệu sau khi xử lý (processed_data): Dữ liệu đã được tiền xử lý
    - Dữ liệu huấn luyện mô hình (training_data): Dữ liệu train/test/val
    - Dữ liệu đầu ra đánh giá (evaluation_data): Kết quả đánh giá mô hình
    """

    def __init__(self, base_path=None):
        # PERF-002: base_path=None -> resolve qua get_data_root() TẠI ĐÂY (lúc
        # khởi tạo instance), không phải giá trị mặc định 'data_warehouse' cố
        # định (phụ thuộc CWD tiến trình) như trước — cho phép test/E2E set
        # EDUDSS_DATA_ROOT để cô lập hoàn toàn dataset/model/training history
        # khỏi kho dữ liệu thật, mà không đổi hành vi mặc định cho runtime bình
        # thường (không set biến môi trường -> vẫn ra đúng data_warehouse/ cũ).
        self.base_path = str(base_path) if base_path else str(get_data_root())
        base_path = self.base_path
        self.models_path = os.path.join(base_path, 'models')
        self.data_path = os.path.join(base_path, 'datasets')
        self.raw_data_path = os.path.join(base_path, 'raw_data')  # Dữ liệu thô đầu vào
        self.processed_data_path = os.path.join(base_path, 'processed_data')  # Dữ liệu sau xử lý
        self.training_data_path = os.path.join(base_path, 'training_data')  # Dữ liệu huấn luyện
        self.evaluation_data_path = os.path.join(base_path, 'evaluation_data')  # Dữ liệu đánh giá
        self.metadata_path = os.path.join(base_path, 'metadata')
        self.history_path = os.path.join(base_path, 'history')
        self.embeddings_path = os.path.join(base_path, 'embeddings')  # Cache embeddings cho RAG
        for path in [
            self.models_path,
            self.data_path,
            self.raw_data_path,
            self.processed_data_path,
            self.training_data_path,
            self.evaluation_data_path,
            self.metadata_path,
            self.history_path,
            self.embeddings_path,
        ]:
            os.makedirs(path, exist_ok=True)

    def _atomic_json_write(self, filepath, data, indent=2):
        """Ghi file JSON an toàn nguyên tử (atomic write) qua file tạm .tmp để
        tránh file bị hỏng nếu bị ngắt tiến trình đột ngột.
        LƯU Ý GIỚI HẠN KIẾN TRÚC: Lưu trữ file cục bộ (local JSON) phù hợp cho
        single-node / prototype demo, chưa thay thế cho CSDL phân tán hỗ trợ
        multi-user concurrency ở cấp enterprise.
        """
        dir_name = os.path.dirname(filepath)
        os.makedirs(dir_name, exist_ok=True)
        tmp_path = f"{filepath}.tmp_{uuid.uuid4().hex}"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            os.replace(tmp_path, filepath)
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            _logger.error("Ghi atomic file JSON thất bại (%s): %s", filepath, e, exc_info=True)
            raise

    def _sanitize_for_json(self, obj):
        """
        Chuyển đổi các kiểu dữ liệu (numpy, pandas, datetime, set, ...) sang
        định dạng tương thích JSON để tránh lỗi khi json.dump.
        """
        if isinstance(obj, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._sanitize_for_json(v) for v in obj]
        if isinstance(obj, np.ndarray):
            return [self._sanitize_for_json(v) for v in obj.tolist()]
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
            return obj.isoformat()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, (pd.Series, pd.Index)):
            return obj.tolist()
        if hasattr(obj, "item") and callable(obj.item):
            try:
                return obj.item()
            except Exception:
                pass
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def generate_id(self, data_str):  # Tạo ID duy nhất dựa trên chuỗi đầu vào
        return hashlib.md5(data_str.encode()).hexdigest()[:12]

    def save_dataset(self, df, dataset_name, description="", data_type="raw", data_source_type=None):
        """
        Lưu một DataFrame mới vào kho dữ liệu.

        Parameters:
        -----------
        df : pd.DataFrame
            DataFrame cần lưu
        dataset_name : str
            Tên dataset
        description : str
            Mô tả dataset
        data_type : str
            Loại dữ liệu: "raw" (thô), "processed" (đã xử lý), "training" (huấn luyện), "evaluation" (đánh giá)
        data_source_type : str, optional
            "synthetic" (mô phỏng) hoặc "real" (thực tế). Mặc định lấy từ df.attrs hoặc suy luận từ data_type/name.
        """
        dataset_id = self.generate_id(f"{dataset_name}_{datetime.now().isoformat()}")

        if data_source_type is None:
            data_source_type = getattr(df, "attrs", {}).get(
                "data_source_type",
                "synthetic" if "sample" in dataset_name.lower() or "demo" in dataset_name.lower() else "real",
            )

        # Chọn đường dẫn dựa trên loại dữ liệu
        if data_type == "raw":
            csv_path = os.path.join(self.raw_data_path, f"{dataset_id}.csv")
        elif data_type == "processed":
            csv_path = os.path.join(self.processed_data_path, f"{dataset_id}.csv")
        elif data_type == "training":
            csv_path = os.path.join(self.training_data_path, f"{dataset_id}.csv")
        elif data_type == "evaluation":
            csv_path = os.path.join(self.evaluation_data_path, f"{dataset_id}.csv")
        else:
            csv_path = os.path.join(self.data_path, f"{dataset_id}.csv")

        df.to_csv(csv_path, index=False)
        metadata = {
            'dataset_id': dataset_id,
            'dataset_name': dataset_name,
            'description': description,
            'data_type': data_type,
            'data_source_type': data_source_type,
            'created_at': datetime.now().isoformat(),
            'n_rows': len(df),
            'n_cols': len(df.columns),
            'columns': df.columns.tolist(),
            'dtypes': df.dtypes.astype(str).to_dict(),
            'file_path': csv_path,
        }
        metadata_path = os.path.join(self.metadata_path, f"{dataset_id}_data.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Tự động ghi log activity
        if data_type == "raw":
            self.log_activity(
                "Tải Dữ liệu", f"Tải lên dataset mới: {dataset_name}", {"rows": len(df), "cols": len(df.columns)}
            )
        elif data_type == "processed":
            self.log_activity(
                "Làm sạch Dữ liệu", f"Lưu dataset đã xử lý: {dataset_name}", {"rows": len(df), "cols": len(df.columns)}
            )
        elif data_type == "advisor":
            self.log_activity("Tư vấn AI", "Tạo kế hoạch học tập mới", {"rows": len(df)})
        elif data_type == "clustered":
            self.log_activity("Phân cụm", f"Lưu kết quả phân cụm: {dataset_name}", {"rows": len(df)})

        return dataset_id, metadata

    def save_raw_data(self, df, dataset_name, description=""):
        """Lưu dữ liệu thô đầu vào."""
        return self.save_dataset(df, dataset_name, description, data_type="raw")

    def save_processed_data(self, df, dataset_name, description="", raw_dataset_id=None):
        """Lưu dữ liệu sau khi xử lý."""
        dataset_id, metadata = self.save_dataset(df, dataset_name, description, data_type="processed")
        if raw_dataset_id:
            metadata['raw_dataset_id'] = raw_dataset_id
            # Cập nhật metadata
            metadata_path = os.path.join(self.metadata_path, f"{dataset_id}_data.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        return dataset_id, metadata

    def update_dataset_description(self, dataset_id, new_description):
        """Cập nhật mô tả cho dataset."""
        metadata_path = os.path.join(self.metadata_path, f"{dataset_id}_data.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, encoding='utf-8') as f:
                    metadata = json.load(f)

                metadata['description'] = new_description

                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                return True, "Cập nhật thành công!"
            except Exception as e:
                return False, f"Lỗi khi cập nhật: {e!s}"
        return False, "Không tìm thấy dataset."

    def save_training_data(
        self, X_train, y_train, X_test, y_test, dataset_name, description="", processed_dataset_id=None
    ):
        """Lưu dữ liệu huấn luyện (train/test split)."""
        # Lưu training set
        train_df = X_train.copy()
        train_df['target'] = y_train
        train_id = self.generate_id(f"{dataset_name}_train_{datetime.now().isoformat()}")
        train_path = os.path.join(self.training_data_path, f"{train_id}_train.csv")
        train_df.to_csv(train_path, index=False)

        # Lưu test set
        test_df = X_test.copy()
        test_df['target'] = y_test
        test_id = self.generate_id(f"{dataset_name}_test_{datetime.now().isoformat()}")
        test_path = os.path.join(self.training_data_path, f"{test_id}_test.csv")
        test_df.to_csv(test_path, index=False)

        metadata = {
            'training_data_id': train_id,
            'test_data_id': test_id,
            'dataset_name': dataset_name,
            'description': description,
            'data_type': 'training',
            'created_at': datetime.now().isoformat(),
            'train_rows': len(train_df),
            'test_rows': len(test_df),
            'train_path': train_path,
            'test_path': test_path,
        }
        if processed_dataset_id:
            metadata['processed_dataset_id'] = processed_dataset_id

        metadata_path = os.path.join(self.metadata_path, f"{train_id}_training.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return train_id, test_id, metadata

    def save_evaluation_data(self, evaluation_results, model_name, training_id, description=""):
        """Lưu dữ liệu đánh giá mô hình."""
        eval_id = self.generate_id(f"eval_{model_name}_{datetime.now().isoformat()}")
        eval_path = os.path.join(self.evaluation_data_path, f"{eval_id}.json")

        metadata = {
            'evaluation_id': eval_id,
            'model_name': model_name,
            'training_id': training_id,
            'description': description,
            'data_type': 'evaluation',
            'created_at': datetime.now().isoformat(),
            'evaluation_results': self._sanitize_for_json(evaluation_results),
            'file_path': eval_path,
        }

        with open(eval_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return eval_id, metadata

    def save_prediction(self, prediction_data):
        """Lưu một bản ghi dự đoán (cho một sinh viên) vào kho.

        Phase 1B: khi EDUDSS_PREDICTIONS_STORE=postgres, PostgreSQL là nơi lưu
        DUY NHẤT cho bản ghi dự đoán này (không ghi đúp vào JSON cục bộ) —
        khi không bật, hành vi JSON cục bộ giữ nguyên như trước."""
        prediction_id = self.generate_id(f"prediction_{datetime.now().isoformat()}")
        training_id = prediction_data.get('training_id', 'unknown')
        prediction_value = prediction_data.get('value') if 'value' in prediction_data else prediction_data.get('label')
        metadata = prediction_data.get('metadata', {})

        if is_postgres_enabled("PREDICTIONS"):
            from dss.db.repositories import prediction_repository

            prediction_repository.save_prediction(
                organization_id=_current_organization_id(),
                training_id=training_id,
                prediction_value=prediction_value,
                student_code=prediction_data.get('student_id')
                or (prediction_data.get('inputs') or {}).get('student_id'),
                input_data=prediction_data.get('inputs', {}),
                confidence=metadata.get('confidence'),
            )
        else:
            prediction_record = {
                'prediction_id': prediction_id,
                # Link to training if available
                'training_id': training_id,
                'predicted_at': datetime.now().isoformat(),
                'input_data': prediction_data.get('inputs', {}),
                # Can be value (reg) or label (clf)
                'prediction': prediction_value,
                # e.g., model name, target, probabilities
                'metadata': metadata,
            }
            self._add_to_history('prediction', prediction_record)

        # Tự động ghi log activity (lịch sử hoạt động hiển thị cho người dùng —
        # khái niệm khác với nơi lưu bản ghi dự đoán thô ở trên, luôn ghi bất
        # kể backend nào đang chủ trì).
        model_name = metadata.get('model_name', 'unknown')
        self.log_activity(
            "Dự đoán", f"Dự đoán cho 1 bản ghi bằng mô hình {model_name}", {"prediction_id": prediction_id}
        )

        return prediction_id

    def save_ai_consultation(self, consultation_data):
        """Lưu phiên tư vấn AI để phục vụ truy xuất/lần tư vấn sau.

        Phase 1B: khi EDUDSS_CONSULTATIONS_STORE=postgres, PostgreSQL là nơi
        lưu DUY NHẤT (không ghi đúp vào JSON cục bộ)."""
        consultation_id = self.generate_id(f"advisor_{datetime.now().isoformat()}")
        student_id = consultation_data.get("student_id", "unknown")
        provider = consultation_data.get("provider", "unknown")
        top_documents = consultation_data.get("top_documents", [])

        if is_postgres_enabled("CONSULTATIONS"):
            from dss.db.repositories import consultation_repository

            consultation_repository.save_consultation(
                organization_id=_current_organization_id(),
                provider=provider,
                student_code=student_id if student_id != "unknown" else None,
                model=consultation_data.get("model_name") or None,
                question=consultation_data.get("rag_query") or None,
                answer=consultation_data.get("generated_plan") or None,
            )
        else:
            payload = {
                "consultation_id": consultation_id,
                "created_at": datetime.now().isoformat(),
                "student_id": student_id,
                "predicted_gpa": consultation_data.get("predicted_gpa"),
                "weaknesses": consultation_data.get("weaknesses", []),
                "provider": provider,
                "model_name": consultation_data.get("model_name", ""),
                "embedding_model": consultation_data.get("embedding_model", ""),
                "rag_query": consultation_data.get("rag_query", ""),
                "top_documents": top_documents,
                "generated_plan": consultation_data.get("generated_plan", ""),
                "metadata": consultation_data.get("metadata", {}),
            }
            self._add_to_history("advisor", payload)

        self.log_activity(
            "Tư vấn AI",
            f"Tạo kế hoạch cho sinh viên {student_id}",
            {
                "consultation_id": consultation_id,
                "provider": provider,
                "doc_count": len(top_documents),
            },
        )
        return consultation_id

    def save_model_training(
        self,
        dataset_id,
        model_pipeline,
        model_name,
        feature_cols,
        target_col,
        metrics,
        X_train=None,
        y_train=None,
        X_test=None,
        y_test=None,
        processed_data=None,
        class_labels=None,
        is_best=False,
        auto_promote=None,
        data_source_type="synthetic",
        split_strategy="random",
        prediction_horizon="next_semester",
        promoted_by=None,
        promotion_reason=None,
        **extra_metadata,
    ):
        """
        Lưu một mô hình đã huấn luyện (dưới dạng pipeline) vào kho.
        TỰ ĐỘNG lưu các loại dữ liệu: training data, evaluation data.

        QUY TẮC QUẢN TRỊ MÔ HÌNH (MODEL GOVERNANCE):
        - Giảng viên huấn luyện chỉ tạo mô hình ở trạng thái Candidate (status="candidate", is_production=False, auto_promote=False).
        - Tuyệt đối không tự động thay đổi con trỏ Production trừ khi auto_promote=True được chỉ định rõ.
        - Khi auto_promote is None (legacy calls trong test cũ), fallback về is_best để tương thích ngược 100%.
        - Chỉ Quản trị viên (Admin) mới có thẩm quyền Promote hoặc Rollback con trỏ Production.
        """
        # training_id PHẢI duy nhất tuyệt đối, không chỉ "khó trùng" — dùng
        # generate_id() (md5 của dataset_id+model_name+timestamp) từng gây lỗi
        # thật: 2 lần lưu CÙNG (dataset_id, model_name) hoàn tất trong CÙNG 1
        # tick đồng hồ hệ thống nhận CÙNG training_id, khiến lần lưu sau ghi đè
        # ÂM THẦM file .joblib/metadata của lần trước (mất bản ghi, xem
        # tests/test_model_registry.py). Uniqueness giờ dựa HOÀN TOÀN vào
        # uuid4 (ngẫu nhiên 122 bit, không phụ thuộc đồng hồ hệ thống) — phần
        # timestamp chỉ giữ lại để dễ đọc/sắp xếp khi liệt kê file trên đĩa,
        # không tham gia vào việc đảm bảo duy nhất.
        training_id = f"train_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex}"
        model_path = os.path.join(self.models_path, f"{training_id}.joblib")
        if not JOBLIB_AVAILABLE or joblib is None:
            raise RuntimeError("Chưa cài joblib — không thể lưu mô hình. Chạy: pip install joblib")
        try:
            joblib.dump(model_pipeline, model_path)
        except Exception as e:
            _logger.error(
                "Ghi file model thất bại (training_id=%s, model=%s): %s", training_id, model_name, e, exc_info=True
            )
            raise RuntimeError(f"Không thể ghi file mô hình: {e}") from e

        # Tự động lưu training data nếu có
        train_id = test_id = None
        if X_train is not None and y_train is not None and X_test is not None and y_test is not None:
            train_id, test_id, _ = self.save_training_data(
                X_train,
                y_train,
                X_test,
                y_test,
                dataset_name=f"{model_name}_training",
                description=f"Training data cho {model_name}",
                processed_dataset_id=dataset_id,
            )

        # Tự động lưu evaluation data
        eval_id, _ = self.save_evaluation_data(
            evaluation_results=metrics,
            model_name=model_name,
            training_id=training_id,
            description=f"Kết quả đánh giá cho {model_name}",
        )

        # Tính mã băm SHA-256 cho artifact mô hình (Mục 28: Artifact Safety)
        model_sha256 = model_hmac = None
        if os.path.exists(model_path):
            model_sha256 = _file_sha256(model_path)
            model_hmac = _artifact_tag(training_id, model_sha256)

        model_key = f"{dataset_id}::{target_col}"
        # MỤC 4: LOẠI BỎ hoàn toàn tự động promote Production khi huấn luyện
        # Vòng đời chuẩn: TRAINED -> CANDIDATE -> EVALUATED -> ADMIN APPROVAL -> PRODUCTION
        should_promote = bool(auto_promote) if auto_promote is not None else bool(is_best)
        status = "production" if should_promote else "candidate"
        training_metadata = {
            'training_id': training_id,
            'dataset_id': dataset_id,
            'model_name': model_name,
            'trained_at': datetime.now().isoformat(),
            'feature_cols': feature_cols,
            'target_col': target_col,
            'metrics': metrics,
            'model_path': model_path,
            'model_sha256': model_sha256,
            'model_hmac': model_hmac,
            'trusted_origin': 'local_training',
            'train_data_id': train_id,
            'test_data_id': test_id,
            'evaluation_id': eval_id,
            'class_labels': self._sanitize_for_json(class_labels) if class_labels is not None else None,
            'model_key': model_key,
            'version': len(self.list_model_versions(dataset_id, target_col)) + 1,
            'is_production': bool(should_promote),
            'status': status,
            'is_best_candidate': bool(is_best),
            'promoted_at': datetime.now().isoformat() if should_promote else None,
            'promoted_by': promoted_by if should_promote else None,
            'promotion_reason': promotion_reason if should_promote else None,
            'data_source_type': data_source_type,
            'split_strategy': split_strategy,
            'prediction_horizon': prediction_horizon,
            **{k: self._sanitize_for_json(v) for k, v in extra_metadata.items()},
        }
        metadata_path = os.path.join(self.metadata_path, f"{training_id}_model.json")
        self._atomic_json_write(metadata_path, training_metadata)
        self._add_to_history('training', training_metadata)

        if should_promote:
            self.set_production_model(
                training_id,
                promoted_by=promoted_by or "System",
                promotion_reason=promotion_reason or "Promoted automatically via auto_promote/best candidate",
            )

        # Tự động ghi log activity
        self.log_activity("Huấn luyện", f"Huấn luyện thành công mô hình {model_name} (status: {status})")

        # Workstream C (ML governance): ADDITIVE, best-effort mirror of this
        # training's metadata into Postgres for provenance/drift querying —
        # the joblib file + training_metadata JSON above remain the one,
        # unconditional source of truth this method has always written;
        # this call is a no-op unless EDUDSS_ML_PROVENANCE_STORE=postgres is
        # explicitly set, and can never fail this method (see
        # dss/services/ml_provenance.py::record_training_provenance).
        try:
            from dss.services import ml_provenance

            ml_provenance.record_training_provenance(
                organization_id=_current_organization_id(),
                training_id=training_id,
                dataset_id=dataset_id,
                target_col=target_col,
                model_name=model_name,
                model_pipeline=model_pipeline,
                feature_cols=feature_cols,
                metrics=metrics,
                status=status,
                model_task_type="classification" if class_labels is not None else "regression",
                model_sha256=model_sha256,
                model_path=model_path,
                X_train=X_train,
                owner=promoted_by,
                created_by=promoted_by,
            )
        except Exception:
            _logger.warning("ML provenance hook raised unexpectedly (training already saved, ignoring)", exc_info=True)

        return training_id, training_metadata

    def _production_index_path(self):
        return os.path.join(self.metadata_path, "_production_index.json")

    def _load_production_index(self):
        path = self._production_index_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save_production_index(self, index):
        self._atomic_json_write(self._production_index_path(), index)

    def set_production_model(self, training_id, promoted_by=None, promotion_reason=None):
        """Chốt 1 model đã lưu làm bản Production DUY NHẤT cho đúng (dataset_id, target_col)
        của nó — chỉ Admin được thực hiện (qua model_registry.promote/rollback).
        Bản Production cũ (nếu có) bị hạ xuống is_production=False, status='archived', không xoá.
        """
        metadata_path = os.path.join(self.metadata_path, f"{training_id}_model.json")
        if not os.path.exists(metadata_path):
            return False, "Không tìm thấy metadata của mô hình."
        try:
            with open(metadata_path, encoding='utf-8') as f:
                meta = json.load(f)
        except json.JSONDecodeError as e:
            _logger.error("Metadata mô hình bị hỏng (training_id=%s): %s", training_id, e, exc_info=True)
            return False, "Metadata mô hình bị hỏng."

        model_key = meta.get('model_key') or f"{meta.get('dataset_id')}::{meta.get('target_col')}"
        index = self._load_production_index()
        prev_training_id = index.get(model_key)
        if prev_training_id and prev_training_id != training_id:
            prev_path = os.path.join(self.metadata_path, f"{prev_training_id}_model.json")
            if os.path.exists(prev_path):
                try:
                    with open(prev_path, encoding='utf-8') as f:
                        prev_meta = json.load(f)
                    prev_meta['is_production'] = False
                    prev_meta['status'] = 'archived'
                    self._atomic_json_write(prev_path, prev_meta)
                except (json.JSONDecodeError, OSError) as e:
                    _logger.warning("Không thể cập nhật status archived cho model cũ (%s): %s", prev_training_id, e)

        meta['is_production'] = True
        meta['status'] = 'production'
        meta['promoted_at'] = datetime.now().isoformat()
        if promoted_by:
            meta['promoted_by'] = promoted_by
        if promotion_reason:
            meta['promotion_reason'] = promotion_reason
        meta['model_key'] = model_key
        self._atomic_json_write(metadata_path, meta)
        index[model_key] = training_id
        self._save_production_index(index)
        return True, "Đã đặt làm Production"

    def get_model_metadata_only(self, training_id):
        """Đọc CHỈ metadata JSON của 1 training_id — không tải artifact .joblib
        (khác load_model_training, vốn tải cả pipeline). Dùng cho các nhu cầu
        chỉ cần đọc thông tin nhẹ, vd. ghi audit log trước/sau khi Promote."""
        metadata_path = os.path.join(self.metadata_path, f"{training_id}_model.json")
        if not os.path.exists(metadata_path):
            return None
        try:
            with open(metadata_path, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_production_model(self, dataset_id, target_col):
        """Trả (pipeline, metadata) của bản Production hiện tại cho (dataset_id, target_col),
        hoặc (None, None) nếu chưa có model nào được huấn luyện cho cặp này."""
        training_id = self.get_production_training_id(dataset_id, target_col)
        if not training_id:
            return None, None
        pipeline, metadata, _msg = self.load_model_training(training_id)
        return pipeline, metadata

    def get_production_training_id(self, dataset_id, target_col):
        """Chỉ đọc con trỏ Production (`_production_index.json`) — KHÔNG load file
        .joblib. Tách riêng để tầng trên (`model_registry.resolve_production`) có
        thể cache phần "tải artifact" theo `training_id` mà vẫn luôn đọc MỚI phần
        "con trỏ đang trỏ vào đâu" ở mỗi lần gọi — đây là phần bắt buộc phải phản
        ánh đúng NGAY sau khi Admin Promote/Rollback, không được cache."""
        return self._load_production_index().get(f"{dataset_id}::{target_col}")

    def list_model_versions(self, dataset_id, target_col):
        """Liệt kê mọi version model đã lưu cho (dataset_id, target_col), mới nhất trước —
        dùng cho màn hình Model Registry (lịch sử version + chọn bản để rollback)."""
        model_key = f"{dataset_id}::{target_col}"
        versions = [
            m
            for m in self.list_models()
            if (m.get('model_key') or f"{m.get('dataset_id')}::{m.get('target_col')}") == model_key
        ]
        versions.sort(key=lambda m: m.get('trained_at', ''), reverse=True)
        return versions

    def _add_to_history(self, record_type, record):
        """Hàm nội bộ để thêm một bản ghi vào file lịch sử dạng JSON."""
        history_file = os.path.join(self.history_path, f"{record_type}_history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, encoding='utf-8') as f:
                    history = json.load(f)  # Handle corrupted JSON
            except json.JSONDecodeError:
                history = []
        else:
            history = []
        history.append(self._sanitize_for_json(record))
        sanitized_history = [self._sanitize_for_json(item) for item in history]
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(sanitized_history, f, indent=2, ensure_ascii=False)

    def log_activity(self, action_type, description, details=None):
        """Lưu lịch sử hoạt động vào activity_history.json và mirror vào activities.json (UI).

        Phase 1C: khi EDUDSS_ACTIVITY_STORE=postgres, PostgreSQL là nơi lưu
        DUY NHẤT (không ghi đúp vào JSON cục bộ) — đọc lại (get_recent_activities/
        get_merged_recent_activities) cũng chuyển nguồn tương ứng, xem bên dưới."""
        activity_record = {
            'activity_id': self.generate_id(f"activity_{datetime.now().isoformat()}"),
            'activity_type': action_type,
            'description': description,
            'details': details or {},
            'timestamp': datetime.now().isoformat(),
        }
        if is_postgres_enabled("ACTIVITY"):
            from dss.db.repositories import activity_log_repository

            activity_log_repository.record_activity(
                organization_id=_current_organization_id(),
                action_type=action_type,
                description=description,
                details=details or {},
            )
            return activity_record['activity_id']
        self._add_to_history('activity', activity_record)
        try:
            activities = self.get_recent_activities(limit=100)
            if not isinstance(activities, list):
                activities = []
            activities.insert(
                0,
                {
                    "id": activity_record['activity_id'],
                    "action": action_type,
                    "details": description,
                    "metadata": details or {},
                    "timestamp": activity_record['timestamp'],
                },
            )
            activities = activities[:100]
            activity_file = os.path.join(self.history_path, 'activities.json')
            with open(activity_file, 'w', encoding='utf-8') as f:
                json.dump(self._sanitize_for_json(activities), f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return activity_record['activity_id']

    def get_history(self, record_type='training', limit=50):
        """Lấy lịch sử của một loại bản ghi (training, prediction, activity) từ file JSON."""
        history_file = os.path.join(self.history_path, f"{record_type}_history.json")
        if not os.path.exists(history_file):
            return []
        try:
            with open(history_file, encoding='utf-8') as f:
                history = json.load(f)  # Handle corrupted JSON
        except json.JSONDecodeError:
            return []
        history.sort(key=lambda x: x.get('timestamp', x.get('trained_at', x.get('predicted_at', ''))), reverse=True)
        return history[:limit]

    def list_datasets(self):
        """Liệt kê tất cả các dataset có trong kho bằng cách đọc các file metadata."""
        datasets = []
        for file in os.listdir(self.metadata_path):
            if file.endswith('_data.json'):
                try:
                    # Skip corrupted files
                    with open(os.path.join(self.metadata_path, file), encoding='utf-8') as f:
                        datasets.append(json.load(f))
                except Exception as e:
                    # ARCH-WH-001 (audit 2026-09): narrowed từ `except BaseException`
                    # — chỉ lỗi đọc/parse file thật (JSONDecodeError/OSError/
                    # UnicodeDecodeError...) mới cần bỏ qua, KHÔNG được nuốt luôn
                    # KeyboardInterrupt/SystemExit như BaseException từng làm.
                    _logger.warning("Bỏ qua file dataset metadata lỗi: %s (%s)", file, e)
        datasets.sort(key=lambda x: x['created_at'], reverse=True)
        return datasets

    def list_models(self):
        """Liệt kê tất cả các mô hình đã được huấn luyện trong kho."""
        models = []
        for file in os.listdir(self.metadata_path):
            if file.endswith('_model.json'):
                try:
                    # Skip corrupted files
                    with open(os.path.join(self.metadata_path, file), encoding='utf-8') as f:
                        models.append(json.load(f))
                except Exception as e:
                    # ARCH-WH-001 (audit 2026-09): xem ghi chú tương tự ở list_datasets().
                    _logger.warning("Bỏ qua file model metadata lỗi: %s (%s)", file, e)
        models.sort(key=lambda x: x['trained_at'], reverse=True)
        return models

    def load_dataset(self, dataset_id):
        """Tải dataset từ kho dựa trên ID."""
        metadata_path = os.path.join(self.metadata_path, f"{dataset_id}_data.json")
        if not os.path.exists(metadata_path):
            return None, "Không tìm thấy metadata của dataset."

        try:
            with open(metadata_path, encoding='utf-8') as f:
                metadata = json.load(f)

            file_path = metadata.get('file_path')
            if not file_path or not os.path.exists(file_path):
                # Fallback check standard paths
                possible_paths = [
                    os.path.join(self.data_path, f"{dataset_id}.csv"),
                    os.path.join(self.processed_data_path, f"{dataset_id}.csv"),
                    os.path.join(self.raw_data_path, f"{dataset_id}.csv"),
                ]
                for p in possible_paths:
                    if os.path.exists(p):
                        file_path = p
                        break

            if file_path and os.path.exists(file_path):
                df = pd.read_csv(file_path)
                return df, metadata
            return None, "File dữ liệu không tồn tại."
        except Exception as e:
            return None, f"Lỗi khi tải dataset: {e!s}"

    def _verify_artifact(self, training_id, model_path, metadata, blob=None):
        """None nếu artifact đáng tin; ngược lại là thông báo lỗi (không tải)."""
        from dss.core.runtime_mode import is_production

        actual = hashlib.sha256(blob).hexdigest() if blob is not None else _file_sha256(model_path)
        expected_sha = metadata.get('model_sha256')
        if expected_sha and not hmac.compare_digest(actual, str(expected_sha)):
            _logger.error("Mã băm SHA-256 không khớp cho model %s", training_id)
            return "Lỗi bảo mật: Artifact mô hình bị biến đổi hoặc hỏng (sai lệch SHA-256)."
        tag = metadata.get('model_hmac')
        if tag:
            if not hmac.compare_digest(_artifact_tag(training_id, actual), str(tag)):
                _logger.error("Chữ ký artifact không hợp lệ cho model %s", training_id)
                return "Lỗi bảo mật: Chữ ký artifact mô hình không hợp lệ."
            return None
        if is_production():
            return (
                "Artifact mô hình chưa được ký (bản cũ). Quản trị viên cần ký lại bằng "
                "DataWarehouse().sign_legacy_models() hoặc huấn luyện lại."
            )
        _logger.warning("Tải artifact chưa ký (chỉ cho phép ngoài production): %s", training_id)
        return None

    def sign_legacy_models(self):
        """Ký các artifact cũ chưa có ``model_hmac`` (chạy MỘT lần, sau khi đã kiểm chứng thư mục mô hình).

        Chỉ ký artifact còn khớp SHA-256 đã lưu (nếu có). Trả về (đã ký, bỏ qua)."""
        signed, skipped = [], []
        if not os.path.isdir(self.metadata_path):
            return signed, skipped
        for name in sorted(os.listdir(self.metadata_path)):
            if not name.endswith("_model.json"):
                continue
            training_id = name[: -len("_model.json")]
            path = os.path.join(self.metadata_path, name)
            try:
                with open(path, encoding="utf-8") as f:
                    metadata = json.load(f)
            except (OSError, ValueError):
                skipped.append(training_id)
                continue
            model_path = os.path.join(self.models_path, f"{training_id}.joblib")
            if metadata.get("model_hmac") or not _SAFE_ID.match(training_id) or not os.path.exists(model_path):
                continue
            actual = _file_sha256(model_path)
            if metadata.get("model_sha256") and metadata["model_sha256"] != actual:
                skipped.append(training_id)
                continue
            metadata.update(model_sha256=actual, model_hmac=_artifact_tag(training_id, actual))
            self._atomic_json_write(path, metadata)
            signed.append(training_id)
        return signed, skipped

    def load_model_training(self, training_id):
        """Tải mô hình và metadata từ kho."""
        metadata_path = os.path.join(self.metadata_path, f"{training_id}_model.json")
        if not os.path.exists(metadata_path):
            return None, None, "Không tìm thấy metadata của mô hình."

        try:
            with open(metadata_path, encoding='utf-8') as f:
                metadata = json.load(f)
        except json.JSONDecodeError as e:
            _logger.error("Metadata mô hình bị hỏng (training_id=%s): %s", training_id, e, exc_info=True)
            return None, None, f"Metadata mô hình bị hỏng: {e}"
        except OSError as e:
            _logger.error("Lỗi đọc file metadata (training_id=%s): %s", training_id, e, exc_info=True)
            return None, None, f"Lỗi đọc file metadata: {e}"

        try:
            if not isinstance(training_id, str) or not _SAFE_ID.match(training_id):
                return None, None, "Mã phiên huấn luyện không hợp lệ."
            # Không tin ``model_path`` trong metadata (có thể trỏ ra ngoài kho): chỉ tải đúng tệp của training_id.
            model_path = os.path.join(self.models_path, f"{training_id}.joblib")
            if os.path.exists(model_path):
                if not JOBLIB_AVAILABLE or joblib is None:
                    return None, None, "Thiếu joblib — không thể tải mô hình (.joblib)."
                with open(model_path, "rb") as f:
                    blob = f.read()  # đọc MỘT lần: kiểm và tải cùng một bản (không đổi tệp xen giữa)
                problem = self._verify_artifact(training_id, model_path, metadata, blob)
                if problem:
                    return None, None, problem
                import io as _io

                pipeline = joblib.load(_io.BytesIO(blob))
                return pipeline, metadata, "Thành công"
            return None, None, "File mô hình không tồn tại."
        except Exception as e:
            return None, None, f"Lỗi khi tải mô hình: {e!s}"

    def get_evaluation_data_for_rag(self, limit=20):
        """Lấy dữ liệu đánh giá để sử dụng trong RAG."""
        evaluations = []
        for file in os.listdir(self.metadata_path):
            if file.endswith('_training.json') or 'eval' in file.lower():
                try:
                    with open(os.path.join(self.metadata_path, file), encoding='utf-8') as f:
                        eval_data = json.load(f)
                        if eval_data.get('data_type') == 'evaluation':
                            evaluations.append(eval_data)
                except Exception as e:
                    # ARCH-WH-001 (audit 2026-09): xem ghi chú tương tự ở list_datasets().
                    _logger.warning("Bỏ qua file evaluation metadata lỗi: %s (%s)", file, e)
        evaluations.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return evaluations[:limit]

    def get_training_history_for_rag(self, limit=20):
        """Lấy lịch sử huấn luyện để sử dụng trong RAG."""
        return self.get_history('training', limit=limit)

    def get_prediction_history_for_rag(self, limit=20):
        """Lấy lịch sử dự đoán để sử dụng trong RAG."""
        return self.get_history('prediction', limit=limit)

    def get_recent_activities(self, limit=10):
        """Đọc activities.json (bản mirror UI), sắp xếp mới nhất trước."""
        if is_postgres_enabled("ACTIVITY"):
            from dss.db.repositories import activity_log_repository

            return activity_log_repository.get_recent_activities(_current_organization_id(), limit=limit)
        try:
            activity_file = os.path.join(self.history_path, "activities.json")
            if os.path.exists(activity_file):
                with open(activity_file, encoding="utf-8") as f:
                    activities = json.load(f)
                    if isinstance(activities, list):
                        activities.sort(
                            key=lambda x: str(x.get("timestamp", "")),
                            reverse=True,
                        )
                        return activities[:limit]
            return []
        except Exception:
            return []

    def get_merged_recent_activities(self, limit=25):
        """
        Gộp activity_history.json + activities.json, bỏ trùng id, luôn sắp theo thời gian mới nhất.
        Đảm bảo dashboard thấy mọi hoạt động vừa ghi (kể cả khi một trong hai file lệch nhịp).
        """
        seen_ids = set()
        merged = []

        # Khi Postgres là nguồn chính cho ACTIVITY, activity_history.json cục bộ
        # không còn được ghi (xem log_activity ở trên) — bỏ qua vòng đọc local
        # này, get_recent_activities() bên dưới đã tự chuyển sang đọc Postgres.
        if not is_postgres_enabled("ACTIVITY"):
            for item in self.get_history("activity", limit=800):
                aid = item.get("activity_id") or item.get("id")
                if aid:
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                merged.append(
                    {
                        "activity_type": item.get("activity_type", "Hoạt động"),
                        "description": item.get("description", ""),
                        "timestamp": item.get("timestamp", ""),
                        "activity_id": aid,
                    }
                )

        try:
            for item in self.get_recent_activities(limit=300):
                aid = item.get("id")
                if aid:
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                merged.append(
                    {
                        "activity_type": item.get("action", "Hoạt động"),
                        "description": item.get("details", ""),
                        "timestamp": item.get("timestamp", ""),
                        "activity_id": aid,
                    }
                )
        except Exception:
            pass

        merged.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        return merged[:limit]


class VectorStore:
    """
    Class quản lý vector store để cache embeddings và tăng tốc RAG.
    Lưu trữ embeddings của documents để không phải tính toán lại mỗi lần.
    """

    def __init__(self, base_path=None):
        # PERF-002: xem ghi chú tương tự trong DataWarehouse.__init__ ở trên.
        self.base_path = str(base_path) if base_path else str(get_data_root() / "embeddings")
        base_path = self.base_path
        os.makedirs(base_path, exist_ok=True)
        self.embeddings_cache = {}  # Cache trong memory
        self.documents_cache = {}  # Cache documents

    def _get_embedding_file_path(self, doc_id, embedding_model_name):
        """Tạo đường dẫn file cho embedding."""
        # Sanitize model name để dùng làm tên file
        safe_model_name = embedding_model_name.replace('/', '_').replace('\\', '_')
        return os.path.join(self.base_path, f"{doc_id}_{safe_model_name}.npy")

    def save_embedding(self, doc_id, embedding, embedding_model_name):
        """Lưu embedding vào disk và cache."""
        file_path = self._get_embedding_file_path(doc_id, embedding_model_name)
        np.save(file_path, embedding)
        cache_key = f"{doc_id}_{embedding_model_name}"
        self.embeddings_cache[cache_key] = embedding
        return file_path

    def load_embedding(self, doc_id, embedding_model_name):
        """Tải embedding từ cache hoặc disk."""
        cache_key = f"{doc_id}_{embedding_model_name}"
        # Kiểm tra cache trong memory trước
        if cache_key in self.embeddings_cache:
            return self.embeddings_cache[cache_key]

        # Nếu không có trong cache, tải từ disk
        file_path = self._get_embedding_file_path(doc_id, embedding_model_name)
        if os.path.exists(file_path):
            embedding = np.load(file_path)
            self.embeddings_cache[cache_key] = embedding
            return embedding

        return None

    def has_embedding(self, doc_id, embedding_model_name):
        """Kiểm tra xem embedding đã được lưu chưa."""
        cache_key = f"{doc_id}_{embedding_model_name}"
        if cache_key in self.embeddings_cache:
            return True
        file_path = self._get_embedding_file_path(doc_id, embedding_model_name)
        return os.path.exists(file_path)

    def save_document(self, doc_id, document):
        """Lưu document vào cache."""
        self.documents_cache[doc_id] = document

    def get_document(self, doc_id):
        """Lấy document từ cache."""
        return self.documents_cache.get(doc_id)

    def clear_cache(self):
        """Xóa cache trong memory (giữ lại trên disk)."""
        self.embeddings_cache.clear()
        self.documents_cache.clear()
