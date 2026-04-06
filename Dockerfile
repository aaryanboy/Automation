FROM python:3.11-slim

# Install system dependencies (ffmpeg required by moviepy/yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces requires running as a non-root user for security
RUN useradd -m -u 1000 user
USER user

# Set environment variables for the user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Change working directory
WORKDIR $HOME/app

# Copy the requirements file and install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy the rest of the application files securely
COPY --chown=user . .

# Pre-create the directory so ffmpeg/downloads won't face permission issues
RUN mkdir -p videos/temp

# Hugging Face routes traffic strictly to port 7860
EXPOSE 7860

# Run the app through gunicorn, bind directly to all interfaces on 7860
# --timeout 300 is essential because youtube uploading & ffmpeg processing can be slow
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--timeout", "300", "app:app"]
