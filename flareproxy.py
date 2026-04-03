import json
import os
import re
import time
import hashlib
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import socket

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191/v1")

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

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_message = json.dumps({"error": str(e)})
            self.wfile.write(error_message.encode("utf-8"))
        finally:
            if session_id:
                try:
                    requests.post(FLARESOLVERR_URL, headers=headers, json={"cmd": "sessions.destroy", "session": session_id}, timeout=10)
                except Exception:
                    pass

    def do_GET(self):
        url = self.path.replace("http://", "https://")
        self.handle_get_request(url)

    def do_CONNECT(self):
        self.send_response(501, "Not Implemented")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        error_message = (
            "CONNECT method is not supported by FlareProxy.\n\n"
            "Please use HTTP URLs instead of HTTPS URLs in your client configuration.\n"
            "Example: http://www.discogs.com/sell/release/265683\n\n"
            "The proxy will automatically convert HTTP requests to HTTPS when forwarding to FlareSolverr, "
            "so your requests will still be secure.\n"
        )
        self.wfile.write(error_message.encode("utf-8"))


if __name__ == "__main__":
    server_address = ("", 8080)
    httpd = HTTPServer(server_address, ProxyHTTPRequestHandler)
    print("FlareProxy adapter running on port 8080")
    httpd.serve_forever()
