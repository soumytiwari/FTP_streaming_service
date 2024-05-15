import socket,select
import tqdm, struct
from Video import VideoPlayer, LiveStreamer, WatchStream


class FTPClient:
    def __init__(self, server_address, port):
        self.server_address = server_address
        self.port = port
        self.mode = 'I' #for binary 'A' for Ascii
        self.timeout = 6
        self.active_port = False # server in active or passive mode

    def connect(self):
        """
        Connects to the FTP server using the control connection.
        """
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_socket.connect((self.server_address, self.port))
        print(self.control_socket.recv(128).decode())# Print welcome message

    def send_command(self, command:str):
        """
        Sends a command to the server through the control connection.
        """
        try:
            self.control_socket.send(command.encode())
            response = self.control_socket.recv(2048).decode()

            print(response)
            return response
        except socket.error as e:
            print(e)
            return None

    def get_connection_data(self, command = None):
        # # Check for data connection information in response (replace with your parsing logic)
        if command:
            if 'port' in command or 'PORT' in command:
                self.data_address, self.data_port = self.parse_port_command(command)
            elif"227" in command:
                self.data_address, self.data_port = self.parse_pasv_response(command)
        else:
            self.data_address = self.server_address
            self.data_port = 20
            
    def handle_commands(self, command:str) -> str:
        try:
            
            self.command = command[:4]
        except:
            self.command = None
        if 'port' in command or 'PORT' in command:
            try :
                self.active_port = True
                self.get_connection_data(command)
            except Exception:
                self.active_port = False
                print('invalid or incomplete argument e.g PORT 127,0,0,1,45,123')

        if 'retr' in command or 'RETR' in command:
            try:
                self.filename = command.split()[1]
            except:
                print('invalid or incomplete argument e.g RETR [filename]')

        if 'strm' in command or 'STRM' in command:
            code = command.split()
            if code[1] == '-l':
                if len(code) >= 4:
                    if code[2] == '-f':
                        self.stream_mode = 'LIVE FILE'
                else : self.stream_mode = 'LIVE'
            elif code[1] == '-f':
                self.stream_mode = 'FILE'
            elif code[1] == '-w':
                self.stream_mode = 'WATCH'
                
        return command

    def handle_response(self,response)->bool:
        if not response : return False
        elif response[:3] == '221': # 221 Goodbye
            return False
        elif response[:3] == '227': # 227 passive mode
            self.active_port = False
            self.get_connection_data(response)
        elif response[:3] == '150': # 150 File Statuse ok
            if not hasattr(self, "data_address"):
                self.get_connection_data() #if not data address then use defualt port (Not Working)
            self.handle_150_response()
            print(self.control_socket.recv(128).decode()) # completion of data transfer
        return True
    

    def run(self):
        while True:
            try :
                command = input(">> ")
                command = self.handle_commands(command)
                if command: 
                    response = self.send_command(command)
                    if not self.handle_response(response):
                        print ('connection closed..')
                        break
            except KeyboardInterrupt:
                print('Key Board interrupted, closing connection..')
                break

    def start_data_socket(self):
        try:
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.active_port:
                self.data_socket.bind((self.data_address, self.data_port))
                self.data_socket.listen(1)
                self.data_socket, addr = self.data_socket.accept()
                return True
            else :
                self.data_socket.connect((self.data_address, self.data_port))
                return True
        except Exception as e:
            print(str(e))
            return False
        
    def stop_data_sock(self):
        self.data_socket.close()
        

    def handle_150_response(self):
        if self.command.upper() == 'LIST':
            self.get_list()
        elif self.command.upper() == 'RETR':
            self.download()
        elif self.command.upper() == 'STRM':
            if self.stream_mode == 'FILE':
                self.get_stream()
            elif self.stream_mode == 'LIVE':
                self.go_live()
            elif self.stream_mode == 'WATCH':
                self.watch_stream()
                print('watch end')

    def get_list(self):
        if self.start_data_socket():
            data = self.data_socket.recv(2048)
            print(data.decode())

    def download(self):
            # while True:
            if self.start_data_socket():
                filesizebytes = self.data_socket.recv(struct.calcsize("L"))
                filesize = struct.unpack("L", filesizebytes)[0]

                with open(self.filename, "ab") as file:
                    # Wrap the response with tqdm to show the progress bar
                    with tqdm.tqdm(total=filesize, unit='B', unit_scale=True, desc=self.filename, ascii=False) as progress_bar:
                        while True:
                            ready, _, _ = select.select([self.data_socket], [], [], self.timeout)
                            if ready:
                                data = self.data_socket.recv(1024*1024)
                                if not data:
                                    break# No more data from server
                                file.write(data)
                            else:
                                print("Timeout occurred. No data received from server.")
                                break # Timeout occurred, exit the loop

                        # Iterate over the response content in chunks
                            progress_bar.update(len(data))
                self.stop_data_sock()

    def get_stream(self):

        # starting connection for data transfer
        if self.start_data_socket():
            try:
                vp = VideoPlayer(self.data_socket)
                vp.start()
                vp.join()
                self.stop_data_sock()
            except Exception as e:
                print(str(e))

    def go_live(self):
        if self.start_data_socket():
            try:
                livestream = LiveStreamer(self.data_socket)
                livestream.start()
                livestream.join()
                self.stop_data_sock()
            except Exception as e:
                print(str(e))
        
    def watch_stream(self):
        if self.start_data_socket():
            try:
                livestream = WatchStream(self.data_socket)
                livestream.start()
                livestream.join()
                self.stop_data_sock()
            except Exception as e:
                print(str(e))


    def parse_port_command(self,command:str):
        # Extract data address and port from the PORT command (replace with your parsing logic)
        data = command.split()[1].split(",")
        data_addr = f"{data[0]}.{data[1]}.{data[2]}.{data[3]}"
        data_port = int(data[4]) * 256 + int(data[5])
        print(f'in parseport {data_addr, data_port}')
        return data_addr, data_port


    def parse_pasv_response(self,pasv_response:str):
        parts = pasv_response.split()
        addr_port_part = parts[-1]
        addr, port_str = addr_port_part.split(':')
        port = int(port_str)
        return addr, port


    def close(self):
        """
        Closes the control connection.
        """
        if self.control_socket:
            self.control_socket.close()


# class Streaming:





if __name__ == "__main__":
    server_address = "172.16.2.116"
    # server_address = "192.168.29.66"
    # server_address = "localhost"
    port = 21
    client = FTPClient(server_address, port)
    client.connect()
    client.run()
    client.close()
