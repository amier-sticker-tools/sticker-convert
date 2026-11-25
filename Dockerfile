FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir rlottie-python pillow
WORKDIR /app
COPY app.py /app/app.py
EXPOSE 7860
CMD ["python", "/app/app.py"]
