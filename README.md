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

### Test sensors

```
ssh jul@192.168.1.218
cd ~/loadcounter
./env/bin/python test-ultrasonic.sensors.py
```

## Files

| File | Description |
|------|-------------|
| `load-counter.py` | Main script — reads sensors, displays on matrix |
| `test-ultrasonic.sensors.py` | Sensor test script (distance + temperature) |
| `fonts/` | BDF bitmap fonts for the matrix display |
| `loadcounter.service` | systemd unit file |
| `setup-service.sh` | One-time service installation (run from Mac) |
| `deploy.sh` | Push code to Pi and restart (run from Mac) |
| `logs.sh` | View service logs (run from Mac) |
