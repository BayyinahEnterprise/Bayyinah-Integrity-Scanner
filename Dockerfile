# Bayyinah scanner as a container: scan or clean a mounted file, offline.
#   docker build -t bayyinah .
#   docker run --rm --network none -v "$PWD:/data:ro" bayyinah scan /data/file.pdf
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/bayyinah
COPY pyproject.toml README.md LICENSE ./
COPY bayyinah_v0.py bayyinah_v0_1.py ./
COPY bayyinah bayyinah
COPY cli cli
COPY domain domain
COPY infrastructure infrastructure
COPY analyzers analyzers
COPY application application
COPY integrations integrations
COPY legacy legacy
RUN pip install --no-cache-dir . && useradd --create-home scanner
USER scanner
WORKDIR /data
ENTRYPOINT ["bayyinah"]
CMD ["--help"]
