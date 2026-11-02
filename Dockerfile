FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd --gid 10001 polsia && useradd --uid 10001 --gid 10001 --create-home polsia
COPY app ./app
RUN mkdir -p /srv/data && chown -R 10001:10001 /srv/app /srv/data
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--workers","1"]
