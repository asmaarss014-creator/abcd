# Dara Parts Universal Server

**One server, two hosting options:**

- Windows PC: run `DaraPartsServer.exe` from the GitHub Actions build.
- Android phone: run `server/server.py` in Termux.

Clients use a browser or the future native Dara Parts client and connect to the same HTTP API. The database stays on whichever device is selected as the server.

## Default test accounts
- admin /
- user /

Change these before real use.

## PC hosting
Run `DaraPartsServer.exe`. It listens on `0.0.0.0:8765` and serves the interface at `http://PC-IP:8765`.

## Phone hosting
In Termux:
```
pkg update
pkg install python
python server.py
```
Connect the PC/phone clients to the phone hotspot and open `http://PHONE-IP:8765`.

## Security
This version is intended for a trusted local LAN/hotspot. Do not port-forward 8765 to the public Internet. For production remote access, add HTTPS/VPN and stronger account-management controls.
