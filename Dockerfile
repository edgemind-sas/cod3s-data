# COD3S Data Framework - Docker Image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml README.md ./
COPY cod3s_data/ ./cod3s_data/

# Install package
RUN pip install --no-cache-dir .

# Create directory for pipelines
RUN mkdir -p /app/pipelines

# Set default command
ENTRYPOINT ["cod3s-data"]
CMD ["--help"]

# Example usage:
# docker build -t cod3s-data .
# docker run -v $(pwd)/examples:/app/pipelines cod3s-data run /app/pipelines/simple_pipeline.yaml
