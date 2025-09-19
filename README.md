# Meshtastic MQTT → Discord Bot

Most basic bridge between a local Meshtastic MQTT server and a Discord
channel or thread.


## Requirements

-   Linux machine (Raspberry Pi works)
-   Discord bot with write permissions in target channel/thread
-   Python 3 with `discord` and `paho-mqtt` modules
-   Local Meshtastic node publishing JSON to MQTT
-   Local MQTT server


## Installation

### 1. (Optional) Virtual environment

``` bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

``` bash
pip install discord paho-mqtt
```

### 3. Configure `meshbot.py`

Edit the following section:

``` python
# ---------- Configuration ----------

# MQTT
BROKER = "127.0.0.1"          # MQTT server IP
PORT = 1883                   # MQTT server port
TOPIC = "msh/EU_868/2/json/#" # Default EU topic

# DISCORD
DISCORD_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
DISCORD_CHANNEL_ID = PUT_DISCORD_CHANNEL_ID_DIGITS_HERE
DISCORD_THREAD_ID = PUT_DISCORD_THREAD_ID_DIGITS_HERE
```

### 4. Run the bot

``` bash
python3 meshbot.py
```
