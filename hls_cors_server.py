#!/usr/bin/env python3
"""
Lightweight CORS-enabled HTTP server for FieldStation42 HLS streaming.
Ensures web browsers and external web applications can stream .m3u8/.ts
files without Cross-Origin (CORS) restrictions.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

class HLSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        
        # Optimize caching and MIME types for HLS live streams
        if self.path.endswith(".m3u8"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        elif self.path.endswith(".ts"):
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Content-Type", "video/mp2t")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Filter high-frequency .ts chunk polling from logs to keep logs clean
        msg = str(args[0]) if args else ""
        if ".ts" in msg:
            return
        super().log_message(format, *args)

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    directory = sys.argv[2] if len(sys.argv) > 2 else "."
    
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(
        server_address,
        lambda *args, **kwargs: HLSRequestHandler(*args, directory=directory, **kwargs)
    )
    httpd.serve_forever()

if __name__ == "__main__":
    main()
