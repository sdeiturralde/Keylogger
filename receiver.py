#######################################
# #       Importar Librerías        # #
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
        # Lee el largo del contenido
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        # Anexar la data recibida al archivo
        with open(LOG_FILE, "ab") as f:   # "ab" = append binary
            f.write(post_data)
            f.write(b"\n--- FIN DE LA SESION ---\n\n")  # Separador

        print(f"Se recibieron {content_length} bytes, añadidos a {LOG_FILE}")

        # Enviar un 200 OK response de vuelta al script (por al librería "requests")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  
    

#######################################
# #              Main               # #
#######################################

server = HTTPServer(('0.0.0.0', 4466), LogHandler)
print(f"Escuchando en http://0.0.0.0:4466, guardando logs a {LOG_FILE}")
server.serve_forever()