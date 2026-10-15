FROM mt5-python-base:latest
USER root

# Ensure unzip is available
RUN apt-get update && apt-get install -y --no-install-recommends unzip && rm -rf /var/lib/apt/lists/*

USER mint
WORKDIR /home/mint

# Ensure symlink for python without spaces
RUN ln -sf "/home/mint/.wine/drive_c/Program Files/Python312" /home/mint/.wine/drive_c/py312

# Copy bot application files
COPY --chown=mint:mint . /home/mint/bot/
WORKDIR /home/mint/bot

# Install python dependencies inside Wine
RUN WINEDEBUG=-all wine /home/mint/.wine/drive_c/py312/python.exe -m pip install --no-cache-dir \
    MetaTrader5 \
    pandas \
    numpy \
    requests \
    pillow \
    python-dotenv

# Start virtual display & run the 62.7% Gold Strategy Bot inside Wine
CMD ["bash", "-c", "Xvfb :99 -screen 0 1024x768x16 & export DISPLAY=:99 && sleep 1 && WINEDEBUG=-all wine /home/mint/.wine/drive_c/py312/python.exe bot.py"]
