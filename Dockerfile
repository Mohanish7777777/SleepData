# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (we don't have a requirements.txt, so install packages directly)
RUN pip install --no-cache-dir flask psutil requests werkzeug

# Copy the current directory contents into the container at /app
COPY . /app

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port 5000
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
