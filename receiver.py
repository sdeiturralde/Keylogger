#######################################
# #         Import Libraries        # #
#######################################

from http.server import HTTPServer, BaseHTTPRequestHandler

#######################################
# #             Variables           # #
#######################################

LOG_FILE = "received_logs.txt"

#######################################
# #              Clases             # #
#######################################

class LogHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Reads the size of the content
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        # Append the received data to the file
        with open(LOG_FILE, "ab") as f:   # "ab" = append binary
            f.write(post_data)
            f.write(b"\n--- END OF SESSION ---\n\n")  # Separator

        print(f"Received {content_length} bytes, added to {LOG_FILE}")

        # Sends a 200 OK response back to the script
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  
    

#######################################
# #              Main               # #
#######################################

server = HTTPServer(('0.0.0.0', 4466), LogHandler)
print(f"Listening on http://0.0.0.0:4466, saving logs in {LOG_FILE}")
server.serve_forever()
