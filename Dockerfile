FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev libffi-dev su-exec

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

RUN adduser -D -u 1001 pawsino && chown -R pawsino:pawsino /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "main.py"]
