FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy and install dependencies first (layer caching — if requirements.txt
# hasn't changed, Docker reuses this layer and skips reinstalling packages)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything the bot actually needs at runtime
COPY bot.py .
COPY tokenizer.py .
COPY knowledge-base .
COPY prompt-base .

# No EXPOSE needed — this bot uses polling, not webhooks

CMD ["python", "bot.py"]
