FROM ubuntu:22.04

# Avoid tzdata interactive prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt update && apt install -y \
    python3 python3-pip python3-tk \
    mpv ffmpeg \
    libgl1-mesa-glx libx11-6 \
    x11-utils \
    pulseaudio \
    libpulse0 \
    && apt clean

# Set working directory
WORKDIR /app

# Copy everything from local repo to container
COPY . .

# Create MPV config dir and copy the mpv.conf
RUN mkdir -p /root/.config/mpv
COPY docker/mpv.conf /root/.config/mpv/mpv.conf

# Install Python dependencies
RUN bash install.sh
# RUN pip3 install --no-cache-dir -r requirements.txt

# Default command
CMD ["bash"]
