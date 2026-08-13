import json
import os
import re
import time
import hashlib
import urllib.parse
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import socket

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191/v1")
CERT_FILE = os.getenv("SSL_CERT_FILE", "cert.pem")
KEY_FILE = os.getenv("SSL_KEY_FILE", "key.pem")


def generate_self_signed_cert(cert_path=CERT_FILE, key_path=KEY_FILE):
    """Generate self-signed certificate if cert and key files do not exist."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return

    # Try using cryptography package
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FlareProxy")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
            .sign(key, hashes.SHA256())
        )
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        print(f"Generated self-signed certificate: {cert_path}, {key_path}")
        return
    except ImportError:
        pass

    # Try using openssl CLI
    import subprocess
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "3650", "-nodes", "-subj", "/CN=FlareProxy"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Generated self-signed certificate using openssl: {cert_path}, {key_path}")
        return
    except Exception:
        pass

    raise RuntimeError(
        "Could not generate self-signed SSL certificate. Please install 'cryptography' "
        f"or 'openssl', or manually place '{cert_path}' and '{key_path}' in the working directory."
    )


def solve_pow(data: str, difficulty: int):
    required_zero_bytes = difficulty // 2
    is_difficulty_odd = (difficulty % 2) != 0
    nonce = 0
    while True:
        text = data + str(nonce)
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        
        is_valid = True
        for i in range(required_zero_bytes):
            if hash_bytes[i] != 0:
                is_valid = False
                break
        
        if is_valid and is_difficulty_odd:
            if (hash_bytes[required_zero_bytes] >> 4) != 0:
                is_valid = False
                
        if is_valid:
            return hash_bytes.hex(), nonce
        
        nonce += 1


class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):

    def handle_get_request(self, url):
        session_id = None
        headers = {"Content-Type": "application/json"}
        try:
            # Create session
            session_resp = requests.post(FLARESOLVERR_URL, headers=headers, json={"cmd": "sessions.create"}, timeout=30)
            session_resp.raise_for_status()
            session_id = session_resp.json().get("session")

            data = {
                "cmd": "request.get",
                "url": url,
                "session": session_id,
                "maxTimeout": 60000
            }

            response = requests.post(FLARESOLVERR_URL, headers=headers, json=data, timeout=70)
            json_response = response.json()
            html = json_response.get("solution", {}).get("response", "")

            # Check if Anubis challenge is present
            challenge_match = re.search(r'<script\s+id="anubis_challenge"[^>]*>(.*?)</script>', html, re.DOTALL)
            if challenge_match:
                try:
                    challenge_json = json.loads(challenge_match.group(1))
                    challenge_data = challenge_json.get("challenge", {})
                    rules = challenge_json.get("rules", {})
                    
                    if rules.get("algorithm") == "fast":
                        ch_id = challenge_data.get("id")
                        random_data = challenge_data.get("randomData")
                        diff = rules.get("difficulty")
                        
                        t0 = int(time.time() * 1000)
                        hash_hex, nonce = solve_pow(random_data, diff)
                        t1 = int(time.time() * 1000)
                        
                        # Find base prefix
                        base_prefix = ""
                        base_prefix_match = re.search(r'<script\s+id="anubis_base_prefix"[^>]*>(.*?)</script>', html, re.DOTALL)
                        if base_prefix_match:
                            bp_str = base_prefix_match.group(1).strip()
                            if bp_str:
                                try:
                                    base_prefix = json.loads(bp_str)
                                except json.JSONDecodeError:
                                    base_prefix = bp_str.strip('"')

                        # Resolve base URL
                        o = urllib.parse.urlparse(url)
                        base_url = f"{o.scheme}://{o.netloc}"
                        
                        if base_prefix and not base_prefix.startswith('http'):
                            base_prefix = base_url + base_prefix
                        elif not base_prefix:
                            base_prefix = base_url
                            
                        base_prefix = base_prefix.rstrip('/')
                            
                        pass_url = f"{base_prefix}/.within.website/x/cmd/anubis/api/pass-challenge"
                        params = urllib.parse.urlencode({
                            "id": ch_id,
                            "response": hash_hex,
                            "nonce": nonce,
                            "redir": url,
                            "elapsedTime": t1 - t0
                        })
                        
                        pass_url_full = f"{pass_url}?{params}"
                        print(f"Solving Anubis challenge: {pass_url_full}")
                        
                        # Submit challenge and let FlareSolverr follow redir
                        data["url"] = pass_url_full
                        response = requests.post(FLARESOLVERR_URL, headers=headers, json=data, timeout=70)
                        json_response = response.json()
                        html = json_response.get("solution", {}).get("response", "")
                except Exception as eval_err:
                    print(f"Failed to process Anubis challenge: {eval_err}")

            self.send_response(response.status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(bytes(html, "utf-8"))
            self.wfile.flush()

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_message = json.dumps({"error": str(e)})
            self.wfile.write(error_message.encode("utf-8"))
            self.wfile.flush()
        finally:
            if session_id:
                try:
                    requests.post(FLARESOLVERR_URL, headers=headers, json={"cmd": "sessions.destroy", "session": session_id}, timeout=10)
                except Exception:
                    pass

    def do_GET(self):
        url = self.path
        if url.startswith("http://"):
            url = "https://" + url[7:]
        elif not url.startswith("https://"):
            host_header = self.headers.get("Host", "")
            if host_header:
                url = f"https://{host_header}{url}"
        self.handle_get_request(url)

    def do_CONNECT(self):
        target_host = self.path.split(":")[0]

        self.send_response(200, "Connection Established")
        self.end_headers()

        try:
            generate_self_signed_cert()
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
            ssl_sock = ssl_context.wrap_socket(self.connection, server_side=True)
        except Exception as e:
            print(f"SSL handshake failed for {self.path}: {e}")
            return

        self.connection = ssl_sock
        self.rfile = ssl_sock.makefile("rb")
        self.wfile = ssl_sock.makefile("wb")

        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                return
            if not self.parse_request():
                return

            url = self.path
            if not (url.startswith("http://") or url.startswith("https://")):
                host_header = self.headers.get("Host", target_host)
                url = f"https://{host_header}{url}"

            self.handle_get_request(url)
        except Exception as e:
            print(f"Error handling request inside CONNECT tunnel: {e}")


if __name__ == "__main__":
    generate_self_signed_cert()
    server_address = ("", 8080)
    httpd = HTTPServer(server_address, ProxyHTTPRequestHandler)
    print("FlareProxy adapter running on port 8080 (HTTP & HTTPS CONNECT supported)")
    httpd.serve_forever()
