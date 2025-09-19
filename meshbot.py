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
# MQTT
# MQTT server IP
BROKER = '127.0.0.1'
# MQTT server PORT
PORT = 1883
# MQTT server TOPIC default: 'msh/EU_868/2/json/#' for EU all messages
# Limit topic for specific node: 'msh/EU_868/2/json/MediumFast/!cb865e2d'
TOPIC = 'msh/EU_868/2/json/#'

# DISCORD
DISCORD_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
DISCORD_CHANNEL_ID = PUT_DISCORD_CHANNEL_ID_DIGITS_HERE
DISCORD_THREAD_ID = PUT_DISCORD_THREAD_ID_DIGITS_HERE

nodes_dict = {}
nodes_lock = threading.Lock() # not sure if this is the best way to make it threads safe


# Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("mqtt-discord")

# Queue for a bridge MQTT->Discord via asyncio
queue: asyncio.Queue = asyncio.Queue()

# ---------- NodeDB --------
# Thread safe NodeDB dict
def get_names(nodeid):
    key = str(nodeid)
    with nodes_lock:
        entry = nodes_dict.get(key)
        if entry:
            fromlong, fromshort = entry
        else:
            fromshort, fromlong = key, "UNKNOWN"
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
# currently it's called upon every new nodeinfo packet
def update_nodedb(nodeid, shortname, longname):
    global nodes_dict # is global needed?
    key = str(nodeid)
    with nodes_lock:
        nodes_dict[key] = [longname, shortname]
        snapshot = dict(nodes_dict)   # save outside thread lock
    save_nodedb(nodes_dict)

# ---------- MQTT ----------
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        log.info("MQTT connected")
        client.subscribe(TOPIC, qos=1)
        log.info(f"Subscribed to: {TOPIC}")
    else:
        log.error(f"MQTT connect failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8", errors="replace").strip()
        data = json.loads(payload_str)
        # if message portnum is a text type let's parse it
        if data["type"] == "text":
            fromshort, fromlong = get_names(str(data["from"]))
            hops = data.get("hops_away")
            if hops is None:
                hops = "0" # Message with hoplimit 0?
            # wrzucamy do kolejki dane + meta
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "topic": msg.topic,
                    "qos": msg.qos,
                    "fromshort": fromshort,
                    "fromlong": fromlong,
                    "hops" : hops,
                    "payload": data["payload"]["text"],
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
    client.on_connect = on_connect
    client.on_message = on_message
    return client

# ---------- Discord ----------
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
            # fallback to a channel instead of a thread
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
                content = f"**MQTT** `{topic}`\n`{ts}`\n```text\n{raw}\n```"

            # Send the message
            await target.send(content)
        except Exception as e:
            log.exception(f"Error sending to discord: {e}")
        finally:
            queue.task_done()

@client_discord.event
async def on_ready():
    log.info(f"Discord connected as {client_discord.user}")
    client_discord.loop.create_task(send_loop())

# ---------- Main loop ----------
async def main():

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
    mqtt_client.connect(BROKER, PORT, keepalive=60)
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

    # Start discord clieant
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

