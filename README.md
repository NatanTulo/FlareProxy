# FlareProxy
FlareProxy is a transparent http proxy adapter that seamlessly forwards client requests to FlareSolverr and bypass Cloudflare and DDoS-GUARD protection.

## Build
FlareProxy is shipped as a OCI container image, and can be built using the [Dockerfile](Dockerfile) provided in the repository root.

```bash
docker build -t flareproxy .
```

## Run
To run it replace the FLARESOLVERR_URL env var with the url of your FlareSolverr instance. FlareProxy runs on the port 8080.
```bash
docker run -e FLARESOLVERR_URL=http://localhost:8191/v1 -p 8080:8080 flareproxy
```

## Usage
Set FlareProxy as a proxy in your browser, changedetection, or client agent. FlareProxy supports both `http://` and `https://` URLs (via HTTP `CONNECT` tunnel interception with automatic self-signed SSL certificate generation).

```bash
curl --proxy 127.0.0.1:8080 https://www.google.com -k
```
You can use it directly as a proxy in [changedetection](https://github.com/dgtlmoon/changedetection.io). Just navigate to settings -> CAPTCHA & Proxies and add `http://flareproxy:8080` (or `http://your-host:8080`) as an extra proxy. You can now use native `https://` links directly without modifying the URL scheme.

## Docker Compose
Add the snippet to your docker compose stack, i.e.:

```yaml
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-info}
      - LOG_HTML=${LOG_HTML:-false}
      - CAPTCHA_SOLVER=${CAPTCHA_SOLVER:-none}
      - TZ=Europe/Rome
#    ports:
#    - "8191:8191"
    restart: always
  flareproxy:
    image: flareproxy
    container_name: flareproxy
    environment:
    - FLARESOLVERR_URL=http://flaresolverr:8191/v1
    - TZ=Europe/Rome
#    ports:
#    - "8080:8080"
    restart: always
```


## Development
1. To run it locally use venv to prepare the development environment:

```bash
python3 -m venv flareproxy
source flareproxy/bin/activate
pip install -r requirements.txt
```
2. Run the proxy using the FLARESOLVERR_URL env var

```bash
FLARESOLVERR_URL=http://localhost:8191/v1 python3 flareproxy.py
```
3. Test it with curl

```bash
curl --proxy 127.0.0.1:8080 http://www.google.com
```

## Related projects
Shoutout to:

- [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr)
- [changedetection](https://github.com/dgtlmoon/changedetection.io)
- [urlwatch](https://github.com/thp/urlwatch)
