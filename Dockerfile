FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py source.py study.py search.py reading.pdf locations.json quran_text.json ./
COPY appendices ./appendices
# Download the embedding model and index the supplied edition during build.
# At runtime, searches run locally using these cached files.
RUN python search.py
CMD ["python","-u","bot.py"]
