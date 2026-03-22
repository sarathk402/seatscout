FROM python:3.12-slim

# Install Chromium dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

# Install Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy app code
COPY . .

# Expose port
EXPOSE 8000

# Run server
CMD ["python", "server.py"]
