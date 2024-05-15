import socket
from log import Console
from FTPserver import Server
import uuid
import threading


class FTP():
    def __init__(self, host="127.0.0.1", port= 21):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, self.port))
        self.clients = {}
        self.frames = {}
        self.lock = threading.Lock()


    def run(self):
        self.sock.listen(5)
        Console.log(f"Server waiting for connection...")
        while True:
            try:
                client_socket, client_address = self.sock.accept()
                client_id = str(uuid.uuid4())  # Generate unique ID for client
                client_thread = Server(host= self.host, connection=(client_socket,client_address), id=client_id,frames= self.frames, clients= self.clients, lock= self.lock )
                client_thread.daemon = True
                client_thread.start()
                self.clients[client_id] = {"address": client_address, "thread": client_thread}
            except Exception as e:
                Console.log(str(e),'critical')
                break
        self.stop()
    
    def stop(self):
        Console.log('Server closed','info')
        self.sock.close()

if __name__=='__main__':
    ftp=FTP(host='172.16.2.116')
    # ftp=FTP(host='192.168.29.66')
    # ftp=FTP(host='localhost')
    ftp.run()
