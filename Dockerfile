FROM mintjetos/metatrader:latest
USER root

# Install xvfb for headless virtual display and wget
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xvfb \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER mint
WORKDIR /home/mint

# Download and install Windows Python 3.12 inside Wine
RUN wget -q https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe && \
    WINEDLLOVERRIDES="mscoree,mshtml=" xvfb-run -a wine python-3.12.8-amd64.exe /quiet InstallAllUsers=1 PrependPath=1 && \
    rm -f python-3.12.8-amd64.exe

# Install python dependencies inside Wine Windows Python
RUN xvfb-run -a wine python -m pip install --no-cache-dir \
    MetaTrader5 \
    pandas \
    numpy \
    requests \
    pillow \
    python-dotenv

# Copy bot files
COPY --chown=mint:mint . /home/mint/bot/
WORKDIR /home/mint/bot

# Run the 62.7% Gold Bot headless 24/7
CMD ["xvfb-run", "-a", "wine", "python", "bot.py"]
