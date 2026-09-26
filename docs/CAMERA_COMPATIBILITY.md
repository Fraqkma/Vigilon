# Camera compatibility

Compatibility is limited to interfaces implemented by this repository and still depends on the vendor/NVR stream profile.

| Interface | Implementation | Verified here |
| --- | --- | --- |
| Synthetic generated frames | Pillow source adapter | Yes; changing frames, preview, simulated incident and evidence |
| Local video file | OpenCV `VideoCapture` with FFmpeg backend; path contained within configured media directory | Yes; generated MJPEG AVI fixture, EOF, and traversal rejection |
| RTSP / RTSPS | OpenCV FFmpeg backend; explicit scheme, resolved-address CIDR allowlist, service-port rejection, open/read timeout | Adapter implemented; no RTSP publisher or physical camera test |
| ONVIF | Not implemented; no discovery or credential probing | No |
| Vendor cloud-only stream | Not implemented | No |

RTSP is administrator-configured; no network discovery or scanning occurs. Supply a URL for a channel the operator is authorized to access. The URL, including embedded credentials if used, is Fernet-encrypted in the database and omitted from API responses. Keep the encryption key outside the database backups and retain it for restore.

An analog camera can work only when its authorized recorder/NVR exposes that channel through RTSP. The API validates RTSP policy in the worker before opening it. The default CIDR allowlist is private IPv4 only and should be narrowed to the actual camera VLAN. Container networking, host DNS, firewall/VLAN routing, credentials, transport mode, codec, and NVR session limits can affect connection success. Docker Desktop cannot guarantee reachability from a container to every host LAN.

The adapter requests FFmpeg open/read timeouts and runs each source in its own worker thread. Real camera/NVR compatibility, all codecs, RTSPS certificate handling, and timeout behavior against a wedged real device remain unverified. No browser RTSP playback is used; browser preview receives authenticated JPEGs from the worker handoff.
