# Meshtastic MQTT → Discord Bot

Most basic bridge between a local Meshtastic MQTT server and a Discord
channel or thread.

## Requirements

-   Linux machine (Raspberry Pi is preferred)
-   Discord bot with write permissions in the target channel/thread
-   Local Meshtastic node publishing JSON to MQTT
-   MQTT server

If you do not have Discord bot or MQTT server running, go to the
[Extras](#Extras) section first.

## Meshbot Installation

### 1. Mandatory system packages

Install Git, Python3 Pip, and Python3 Virtual Environment modules if
missing.

``` bash
sudo apt install python3-pip python3-venv git
```

### 2. Prepare application folder

``` bash
sudo mkdir /opt/meshbot
sudo chown pi:pi /opt/meshbot
```

### 3. Clone Meshbot repository

``` bash
cd /opt/meshbot
git clone https://github.com/d3cker/MeshMQTTDiscord.git .
```

Note: Notice the dot at the end of the command!

### 4. Create and activate virtual environment, install requirements and generate config template

``` bash
cd /opt/meshbot
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
python3 ./meshbot.py
```
Note: Final command will create default `meshbot.config` file. 

## Meshbot Configuration

### 1. Edit configuration variables in `meshbot.config` file

``` json
{
    "mqtt_server": "127.0.0.1",
    "mqtt_port": 1883,
    "mqtt_topic": "msh/EU_868/2/json/#",
    "mqtt_user": "",
    "mqtt_password": "",
    "discord_token": "",
    "discord_channel_id": 0,
    "discord_thread_id": 0
}
```

-   mqtt_server - MQTT server IP.
-   mqtt_port - MQTT server port. Numeric value.
-   mqtt_topic - MQTT server topic. Default: `msh/EU_868/2/json/#` for
    all EU messages. Limit topic for a specific node like:
    `msh/EU_868/2/json/MediumFast/!cb865e2d` if needed.
-   mqtt_user - MQTT username. Leave blank if the server doesn't require
    username and password.
-   mqtt_password - MQTT password. Leave blank if the server doesn't
    require password.
-   discord_token - Discord bot token.
-   discord_channel_id - Discord channel ID. Numeric value, must be
    other than 0.
-   discord_thread_id - Discord thread ID. Numeric value, if left 0 then
    messages will fallback to the channel.

### 2. Configure systemd

``` bash
sudo cp meshbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable meshbot.service
```

### 3. Run the bot (systemd) - default

``` bash
sudo systemctl start meshbot
```

Check meshbot service status:

``` bash
systemctl status meshbot.service
```

View live logs from meshbot:

``` bash
journalctl -u meshbot.service -e -f
```

Note: Optionally, if you want to run the bot without systemd, you may
start it manually:

``` bash
sudo systemctl stop meshbot.service
cd /opt/meshbot
source venv/bin/activate
python3 meshbot.py
```

## Extras

### Discord bot configuration.

This section describes how to create a Discord bot and retrieve Channel
ID and Thread ID.

1.  Log in to the Discord [developer
    console](https://discord.com/developers/application) and create a
    new application (New Application).
2.  Invite the bot to the server.

Once an application is created, select it from the "Applications" menu.
Go to "OAuth2" on the left menu. In the "**SCOPES**" section select the
**bot** checkbox. A new section "**BOT PERMISSIONS**" will appear.
Select "**Send Messages**" and "**Send Messages in Threads**"
checkboxes. Copy the generated URL and open it in a new browser tab.
Select the server for the bot to join.

3.  Generate bot token

Go to "Bot" on the left menu. Click "Reset token" to generate a new one.
Confirm your identity and follow on-screen instructions. The token value
will be visible only once, copy it and save it somewhere for future
configuration.

4.  Become a developer in Discord.

This step is necessary to get Channel ID and Thread ID. In Discord UI
click **Settings(⚙)** -\> **Advanced** -\> **Developer Mode**. Now you
can right-click on the channel and thread to get their IDs.

### MQTT minimal server configuration.

This section describes how to run a local MQTT server on port 1883 with
no username and password.

1.  Install MQTT server on your host:

``` bash
sudo apt install -y mosquitto mosquitto-clients
```

2.  Configure MQTT server.

Create `/etc/mosquitto/conf.d/local.conf` with the following contents:

``` bash
listener 1883
allow_anonymous true
```

Check if your mosquitto config `/etc/mosquitto/mosquitto.conf` looks 
similar to this:

``` bash
# Place your local configuration in /etc/mosquitto/conf.d/
#
# A full description of the configuration file is at
# /usr/share/doc/mosquitto/examples/mosquitto.conf.example
pid_file /run/mosquitto/mosquitto.pid
persistence true
persistence_location /var/lib/mosquitto/
log_dest file /var/log/mosquitto/mosquitto.log
include_dir /etc/mosquitto/conf.d
```

3.  Start/restart your MQTT server

``` bash
sudo systemctl restart mosquitto.service
```

### Meshtastic Node configuration

This section describes how to configure your node to support the local
MQTT server. WiFi support is recommended to avoid using the application
proxy. This solution was tested on a Raspberry Pico 2W node.

In the Android Meshtastic app, go to Node configuration (⚙) and select
MQTT module configuration. Enter the **address** of your MQTT server (for
example 10.8.0.1). If your MQTT server uses a different port than 1883,
then the address should include it (for example 10.8.0.1:11883). Select
"**JSON output enabled**". If you do not have a WiFi module in your node,
select "Proxy to client enabled" - this will work only if your phone and
MQTT are able to see each other on the network. Confirm changes.

Go back to the main configuration menu and choose "Channels". Select the
default channel and enable "**Uplink enabled**". Confirm changes.
