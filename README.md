# awtrix-screen-homeassistant

sensor:
  - platform: custom_screen_sensor
    name: Custom Sensor 1
    api_endpoint: http://ip/api/screen
    scan_interval: 10  # Custom scan interval in seconds