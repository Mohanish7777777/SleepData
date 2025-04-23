# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly since no requirements.txt is provided
RUN pip install --no-cache-dir flask psutil requests werkzeug

# Copy app code into the container
COPY . /app

# Create uploads directory (in case your app saves files)
RUN mkdir -p /app/uploads

# Expose port Flask will run on
EXPOSE 5000

# Command to run the app (ensure your main file is named app.py)
CMD ["python", "app.py"]
