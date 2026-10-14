FROM python:3.12-slim
WORKDIR /simulator
COPY simulator/__init__.py simulator/lms_cms_simulator.py ./simulator/
RUN useradd --system --uid 999 --create-home simulator
USER 999
EXPOSE 8765
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)"]
CMD ["python", "-m", "simulator.lms_cms_simulator", "--port", "8765"]
