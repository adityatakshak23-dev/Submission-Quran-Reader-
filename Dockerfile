FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py source.py reading.pdf locations.json ./
COPY appendices ./appendices
CMD ["python","-u","bot.py"]
