FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY startup.sh ./
RUN chmod +x /app/startup.sh

ENV PORT=8000
EXPOSE 8000

CMD ["/app/startup.sh"]