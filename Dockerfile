FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
RUN mkdir -p /data
EXPOSE 8080
CMD ["python", "app.py"]
