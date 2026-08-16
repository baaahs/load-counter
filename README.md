# Load Counter

Ultrasonic distance counter using two US-100 sensors displayed on a 32x64 RGB LED matrix. Runs on a Raspberry Pi with an Adafruit RGB Matrix HAT.

## Hardware

- Raspberry Pi (with Adafruit RGB Matrix HAT)
- 2x US-100 ultrasonic sensors (connected via USB serial: `/dev/ttyUSB0`, `/dev/ttyUSB1`)
- 32x64 RGB LED matrix panel

## Setup

### On the Pi

Make sure the virtualenv at `~/loadcounter/env` has the dependencies installed:

```
pip install adafruit-circuitpython-us100 pyserial rgbmatrix
```

### Install as a service (from your Mac)

```
./setup-service.sh
```

This installs a systemd service that starts on boot and auto-restarts on crash.

## Usage

### Deploy code changes

Edit the Python files locally, then push to the Pi and restart:

```
./deploy.sh
```

### View logs

```
./logs.sh              # live tail (Ctrl+C to stop)
./logs.sh last         # last 100 lines
./logs.sh last 500     # last N lines
./logs.sh prev         # logs from previous boot
./logs.sh today        # today's logs
./logs.sh status       # service status
```

### Counter event logs

Count events are appended as JSON Lines on the Pi:

```
/var/lib/loadcounter/events.jsonl
```

Logged event names are `counter_triggered`, `manual_number_changed`, and
`counter_reset`.

The iPhone app's History screen reads this same file through a paginated BLE
characteristic. It does not create or maintain a second event log on the Pi.
When no Pi is connected, the same screen can generate deterministic sample data
on the iPhone to test its charts, filters, statistics, and PDF reports offline.

### Control from your Mac keyboard

Run the remote keyboard controller from this repo:

```
./loadcounter-remote.py
```

It opens one SSH connection to `jul@raspberry.local` and sends the same commands
the Bluetooth keyboard listener writes on the Pi. Use the arrow keys, Return,
Escape, Space, digits, `.`, Backspace, `r`, `y`, and `n`. Press `q` or Ctrl+C to
quit the Mac controller.

For one-shot commands:

```
./loadcounter-remote.py --send esc no enter
```

### Control from iPhone over Bluetooth

Open the SwiftUI app project in Xcode:

```
ios/LoadCounterRemote/LoadCounterRemote.xcodeproj
```

Run it on the iPhone, then tap Connect. The Pi advertises as `LoadCounter`
through the `loadcounter-ble.service` systemd service.

### Test sensors

```
ssh jul@192.168.1.218
cd ~/loadcounter
./env/bin/python test-ultrasonic.sensors.py
```

### Run unit tests

```
python3 -m unittest discover -s tests -v
```

## Files

| File | Description |
|------|-------------|
| `load-counter.py` | Main script — reads sensors, displays on matrix |
| `loadcounter-remote.py` | Mac-side CLI keyboard controller over SSH |
| `loadcounter-ble.py` | Pi-side Bluetooth Low Energy command bridge |
| `test-ultrasonic.sensors.py` | Sensor test script (distance + temperature) |
| `fonts/` | BDF bitmap fonts for the matrix display |
| `loadcounter.service` | systemd unit file |
| `setup-service.sh` | One-time service installation (run from Mac) |
| `deploy.sh` | Push code to Pi and restart (run from Mac) |
| `logs.sh` | View service logs (run from Mac) |
