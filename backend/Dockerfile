FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 nexora && useradd --uid 10001 --gid nexora --create-home nexora
COPY pyproject.toml ./
COPY requirements.lock ./
RUN python -c "import subprocess, sys, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '-c', 'requirements.lock', *deps], check=True)"
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
USER nexora
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
