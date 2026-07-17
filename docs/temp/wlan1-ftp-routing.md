# Temporary wlan1 route for FTP access

If the Pi is connected to a second Wi-Fi network on `wlan1`, you can make that interface the preferred route temporarily so outbound traffic, including FTP uploads, uses that connection.

The gateway IP in this command may be different on your network. Replace `192.168.43.1` with the actual gateway for your `wlan1` Wi-Fi network.

```bash
sudo ip route replace default via 192.168.43.1 dev wlan1 metric 100
```

This only changes the preferred route while it is in effect. If you need to verify the active route afterward, run:

```bash
ip route
```
