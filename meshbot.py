# MeshtasticMQTT -> Discord bot
# by d3cker
# Visit: https://meshtastic.info.pl
# LowerSilesianMesh Discord: https://discord.gg/F4tYfHCj9s
# License: Do whatever you want.

import os
import json
import asyncio
import logging
import signal
import threading
from datetime import datetime
import paho.mqtt.client as mqtt
import discord

# ---------- Configuration ----------
# All variables are configures in meshbot.config file. Do not edit them here. 
# MQTT
MQTT_BROKER = '' # MQTT server IP
MQTT_PORT = 0    # MQTT server port
# MQTT server topic, default: 'msh/EU_868/2/json/#' for EU all messages
# Limit topic for specific node: 'msh/EU_868/2/json/MediumFast/!cb865e2d'
MQTT_TOPIC = ''
# MQTT Username and Password. Leave it blank if serever doesn't require them
MQTT_USER = ""
MQTT_PASSWORD = ""
# Discord
DISCORD_TOKEN = ""      # Discord Bot token
DISCORD_CHANNEL_ID = 0  # Discord channel ID
DISCORD_THREAD_ID = 0   # Discord thread ID, set it to 0 if you want to send message to a channel instead

# ---------- Config file
def check_and_create_config():
    config_file = "meshbot.config"
    
    if not os.path.exists(config_file):
        default_config = {
            "mqtt_server": "127.0.0.1",
            "mqtt_port": 1883,
            "mqtt_topic" : "msh/EU_868/2/json/#",
            "mqtt_user": "",
            "mqtt_password": "",
            "discord_token": "",
            "discord_channel_id": 0,
            "discord_thread_id": 0
        }

        try:
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
            log.info(f"Created default config file: {config_file}")
            exit(0)            
        except Exception as e:
            log.error(f"Failed to create config file: {e}")
            exit(1)
    else:
        log.info(f"Config file {config_file} already exists")
        return True

def load_config():
    global MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC
    global DISCORD_TOKEN, DISCORD_CHANNEL_ID, DISCORD_THREAD_ID
    
    config_file = "meshbot.config"
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Map string values
        MQTT_BROKER = config.get("mqtt_server", "")
        MQTT_USER = config.get("mqtt_user", "")
        MQTT_PASSWORD = config.get("mqtt_password", "")
        MQTT_TOPIC = config.get("mqtt_topic", "")
        DISCORD_TOKEN = config.get("discord_token", "")
        
        # Map and validate numeric values
        try:
            mqtt_port = config.get("mqtt_port", 1883)
            if isinstance(mqtt_port, str):
                if mqtt_port.isdigit():
                    MQTT_PORT = int(mqtt_port)
                else:
                    raise ValueError(f"mqtt_port must be numeric, got: {mqtt_port}")
            else:
                MQTT_PORT = int(mqtt_port)
        except (ValueError, TypeError) as e:
            log.error(f"Invalid mqtt_port: {e}")
            MQTT_PORT = 1883  # fallback to default
        
        try:
            discord_channel_id = config.get("discord_channel_id", 0)
            if isinstance(discord_channel_id, str):
                if discord_channel_id.isdigit():
                    DISCORD_CHANNEL_ID = int(discord_channel_id)
                else:
                    raise ValueError(f"discord_channel_id must be numeric, got: {discord_channel_id}")
            else:
                DISCORD_CHANNEL_ID = int(discord_channel_id)
        except (ValueError, TypeError) as e:
            log.error(f"Invalid discord_channel_id: {e}")
            DISCORD_CHANNEL_ID = 0  # fallback to default
        
        try:
            discord_thread_id = config.get("discord_thread_id", 0)
            if isinstance(discord_thread_id, str):
                if discord_thread_id.isdigit():
                    DISCORD_THREAD_ID = int(discord_thread_id)
                else:
                    raise ValueError(f"discord_thread_id must be numeric, got: {discord_thread_id}")
            else:
                DISCORD_THREAD_ID = int(discord_thread_id)
        except (ValueError, TypeError) as e:
            log.error(f"Invalid discord_thread_id: {e}")
            DISCORD_THREAD_ID = 0  # fallback to default
        
        log.info("Configuration loaded successfully")
        log.info(f"MQTT: {MQTT_BROKER}:{MQTT_PORT} (user: {MQTT_USER})")
        log.info(f"Discord: Channel ID {DISCORD_CHANNEL_ID}, Thread ID {DISCORD_THREAD_ID}")
        return True
        
    except FileNotFoundError:
        log.error(f"Config file {config_file} not found") # this should not happen
        return False
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in config file: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        return False


# NodeDB dict
nodes_dict = {}
nodes_lock = threading.Lock() # not sure if this is the best way to make it threads safe

# ---------- Logs and queue
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("mqtt-discord")

# Queue for a bridge MQTT->Discord via asyncio
queue: asyncio.Queue = asyncio.Queue()

# ---------- NodeDB --------
# Helper function to convert decimal nodeid to lowercase hex
def nodeid_to_hex(nodeid):
    try:
        decimal_value = int(nodeid)
        hex_value = hex(decimal_value)[2:]  # Remove '0x' prefix
        return hex_value.lower()
    except ValueError:
        # If conversion fails, return original value
        return str(nodeid).lower()

# Thread safe NodeDB dict
def get_names(nodeid):
    key = str(nodeid)
    with nodes_lock:
        entry = nodes_dict.get(key)
        if entry:
            fromlong, fromshort = entry
        else:
            node_hex_value = nodeid_to_hex(nodeid)
            fromshort = node_hex_value[-4:]
            fromlong = "Meshtastic " + fromshort + " (!" + node_hex_value + ")"
    return fromshort, fromlong

# Load NodeDB JSONL
def load_nodedb():
    loaded_nodes = {}
    try:
        with open('nodedb.jsonl','r') as f:
            for line in f:
                obj = json.loads(line)
                loaded_nodes.update(obj)
        log.info("Loaded NodeDB")
        return loaded_nodes
    except Exception as e:
        log.error(f"Failed to load NodeDB: {e}")
        nodes_dict['-1'] = ['NONE','NONE']
        return nodes_dict

# Update NodeDB JSONL with new nodeinfo
def save_nodedb(data):
    try:
        with open('nodedb.jsonl', 'w') as f:
            for key,value in data.items():
                json_line = json.dumps({key: value})
                f.write(json_line + '\n')
        f.close()
        log.info("Saved NodeDB")
    except Exception as e:
        log.error(f"Failed to save NodeDB: {e}")

# Update dict and NodeDB - this should be scheduled at some point
# currently it's called upon every new/updated nodeinfo content
def update_nodedb(nodeid, shortname, longname):
    key = str(nodeid)
    new_key = [ longname, shortname ]
    with nodes_lock:
        old_key = nodes_dict.get(key)
        if old_key != new_key:
            nodes_dict[key] = new_key
            snapshot = dict(nodes_dict)   # previously it was outside thread lock, is it still needed?
            save_nodedb(snapshot)
        else:
            log.info("Nodeinfo already exists in NodeDB. Skipping save.")


# ---------- MQTT ----------
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        log.info("MQTT connected")
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info(f"Subscribed to: {MQTT_TOPIC}")
    else:
        log.error(f"MQTT connect failed: {reason_code}")

def on_message(client, userdata, msg):    
    try:
        payload_str = msg.payload.decode("utf-8", errors="replace").strip()
        data = json.loads(payload_str)
        # if message portnum is a text type let's parse it
        if data["type"] == "text":
            fromshort, fromlong = get_names(str(data["from"]))
            hops_away = data.get("hops_away")
            hop_start = data.get("hop_start")
            if hop_start is None:
                hop_start = "0" # This should not happen
            if hops_away is None:
                hops = "0/0" # Message with hoplimit 0?
            else:
                hops = str(hops_away) + "/" + str(hop_start)
            
            # Safely extract text payload
            text_payload = ""
            if isinstance(data["payload"], dict) and "text" in data["payload"]:
                text_payload = data["payload"]["text"]
            else:
                log.warning(f"Invalid text payload format: {data['payload']}")
                text_payload = str(data["payload"])
            
            # add data and meta to the queue
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "topic": msg.topic,
                    "qos": msg.qos,
                    "fromshort": fromshort,
                    "fromlong": fromlong,
                    "hops" : hops,
                    "payload": text_payload,
                    "raw": payload_str,
                    "ts": datetime.utcnow().isoformat() + "Z",
                }),
                userdata["loop"],
            )
        elif data["type"] == "nodeinfo":
            longname = data["payload"]["longname"]
            shortname = data["payload"]["shortname"]
            nodeid = str(data["from"])
            log.info("New nodeinfo: " + longname + " [" + shortname + "] (" + nodeid + ")")
            update_nodedb(nodeid, shortname, longname)
    except json.JSONDecodeError:
        log.warning("Wrong JSON, sending RAW data as a message")
        asyncio.run_coroutine_threadsafe(
            queue.put({
                "topic": msg.topic,
                "qos": msg.qos,
                "fromshort": None,
                "fromshort": None,
                "hops" : None,
                "payload": None,
                "raw": msg.payload.decode("utf-8", errors="replace"),
                "ts": datetime.utcnow().isoformat() + "Z",
            }),
            userdata["loop"],
        )

def make_mqtt_client(loop: asyncio.AbstractEventLoop) -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="mqtt-to-discord-bridge",
        userdata={"loop": loop},
    )

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message
    return client

# ---------- Discord -------
INTENTS = discord.Intents.none()
client_discord = discord.Client(intents=INTENTS)

async def send_loop():
    # Gets message from the queue and publish to Discord
    await client_discord.wait_until_ready()
    if DISCORD_CHANNEL_ID == 0:
        log.error("DISCORD_CHANNEL_ID is missing!")
        return

    try:
        target = None
        if DISCORD_THREAD_ID:
            # Thread must exist (Thread)
            target = await client_discord.fetch_channel(DISCORD_THREAD_ID)
            if not isinstance(target, discord.Thread):
                log.error("DISCORD_THREAD_ID is not a thread!")
                return
            # try archived thread (requires permissions)
            if target.archived:
                try:
                    await target.edit(archived=False)
                except discord.Forbidden:
                    log.warning("Can't unarchive the thread!")
        else:
            # Fallback to channel
            target = await client_discord.fetch_channel(DISCORD_CHANNEL_ID)
    except discord.NotFound:
        log.error("No channel/thread with given ID or missing Guild")
        return
    except discord.Forbidden:
        log.error("Permission denied to thread/channel.")
        return

    while not client_discord.is_closed():
        item = await queue.get()
        try:
            topic = item["topic"]
            ts = item["ts"]
            fromshort = item["fromshort"]
            fromlong = item["fromlong"]
            hops = item["hops"]
            # Shorten long messages as Discord allows 2000 chars (to be verified)
            def clamp(txt: str, limit: int = 1800) -> str:
                return txt if len(txt) <= limit else txt[:limit] + " …[truncated]"

            if item["payload"] is not None:
                pretty = json.dumps(item["payload"], ensure_ascii=False, indent=2)
                content = f"**{fromshort}** `[ {fromlong} ]` `[ hops: {hops} ]`\n```json\n{clamp(pretty)}\n```"
            else:
                raw = clamp(item["raw"])
                content = f"**MQTT RAW** `{topic}`\n`{ts}`\n```text\n{raw}\n```"

            # Wysyłka
            await target.send(content)
        except Exception as e:
            log.exception(f"Error sending to discord: {e}")
        finally:
            queue.task_done()

@client_discord.event
async def on_ready():
    log.info(f"Discord connected as {client_discord.user}")
    # Start queue consumer
    client_discord.loop.create_task(send_loop())

# ---------- Main loop ----------
async def main():

    if check_and_create_config():
        if not load_config():
            log.error("Aborting.")
            exit(1)
    
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN")
    if DISCORD_CHANNEL_ID == 0:
        raise RuntimeError("Missing DISCORD_CHANNEL_ID (digit!)")

    loop = asyncio.get_running_loop()

    global nodes_dict
    nodes_dict = load_nodedb()
    log.info(f"Loaded {len(nodes_dict)} nodes from NodeDB")
    # MQTT in a separate thread (paho uses threads)
    mqtt_client = make_mqtt_client(loop)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    # Clear exit
    stop_event = asyncio.Event()

    def _stop(*_):
        log.info("Exitting…")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows
            pass

    # Start discord client
    discord_task = asyncio.create_task(client_discord.start(DISCORD_TOKEN))

    # Wait for stop signal
    await stop_event.wait()

    # Do the clean up
    await client_discord.close()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    await asyncio.gather(discord_task, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

