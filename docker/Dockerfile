FROM python:3.11-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt update && apt install -y \
    python3-tk \
    mpv ffmpeg \
    libgl1-mesa-glx libx11-6 \
    x11-utils \
    pulseaudio \
    libpulse0 \
    && apt clean

WORKDIR /app

COPY . .

# Create MPV config dir and copy the mpv.conf
RUN mkdir -p /root/.config/mpv
COPY docker/mpv.conf /root/.config/mpv/mpv.conf

# Use install script - will get python dependencies
RUN FS42_SKIP_API_KEY_SETUP=1 bash install.sh

ENTRYPOINT ["bash", "docker/entrypoint.sh"]
CMD ["bash"]
