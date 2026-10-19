FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps ./apps
COPY config ./config
COPY utils ./utils
COPY templates ./templates
COPY static ./static
COPY manage.py entrypoint.sh ./
RUN SECRET_KEY=build-only-not-used-at-runtime DEBUG=False DATABASE_URL=sqlite:////tmp/build.sqlite3 python manage.py collectstatic --noinput
EXPOSE 3000
CMD ["sh", "entrypoint.sh"]
