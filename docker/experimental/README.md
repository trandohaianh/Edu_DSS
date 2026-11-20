# Dockerfile thử nghiệm

Không dùng cho bản phát hành. Image chính được build từ `Dockerfile` ở gốc repo.

- `Dockerfile.torch210-experimental`: thử torch 2.10 CPU trên cùng cấu trúc multi-stage.
- `Dockerfile.c121-test`: kiểm tra phụ thuộc C1.2.1, dựa trên image cục bộ `edudss:c121-dependency-test`.

Build từ gốc repo (build context là `.`):

```bash
docker build -f docker/experimental/Dockerfile.torch210-experimental -t edudss:torch210-experimental .
```
