FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    HF_HOME=/tmp/huggingface

WORKDIR /app

RUN groupadd --system rag \
    && useradd --system --gid rag --home-dir /app --shell /usr/sbin/nologin rag

COPY requirements.txt .

# 显式安装 CPU 版 PyTorch，避免默认 Linux wheel 引入不需要的 CUDA 运行库。
RUN python -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.13.0 \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

USER rag

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
