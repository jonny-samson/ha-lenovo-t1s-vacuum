# Changelog

## 1.0.1

### Added
- Manual controls: **Drive forward**, **Drive back**, **Turn left**, **Turn right** buttons and the
  `lenovo_t1.drive` service (direction, optional duration). The burst is sent from the connection thread
  and does not block Home Assistant.
- **Cancel dock** button.
- Wi-Fi diagnostics (network, signal quality, IP and MAC) and firmware version sensors, queried after
  connecting and every five minutes.
- Fourth consumable: **Sensors life remaining** and **Reset sensors life**.
- **Problem** binary sensor, on whenever the vacuum reports a fault.
- **Stop** on the vacuum entity (`21017 stop`; not verified on the real device).

### Fixed
- Docked at 100% (mode `fullcharge`) showed as idle instead of docked.
- Cleaned area and cleaning time no longer fall back to 0 between cleans; they hold the last clean's value
  until the next clean starts. Cleaning time is now whole minutes.
- After connecting, the startup queries are spread over a few seconds instead of being sent at once.

## 1.0.0

First release.
