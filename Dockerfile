FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CMD ["gunicorn", "-w", "1", "--timeout","120","-b", "0.0.0.0:5000", "app:app"]

CMD ["gunicorn", "-w", "3", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]