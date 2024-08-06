from log import Console
import time,threading,socket,os
import random
import string
from StreamingServer import FileStreamer, LiveStreamer
from struct import pack
import collections, queue


CRLF = '\r\n'

class Server(threading.Thread):
    def __init__(self,host, connection,id, frames, clients, lock):
        self.host = host
        self.clientID = id
        conn,addr = connection
        self.conn :socket.socket= conn
        self.addr = addr
        self.frames:dict = frames
        self.clients:dict = clients
        self.lock:threading.Lock = lock
        self.encoding="utf-8"
        self.pasv_mode = False
        self.authrized = False
        # self.rest = False
        self.mode = 'I' #ASCII or 'I' Binary
        # self.basedir = os.path.abspath('C:\\Users\\Utkarsh\\Videos\\')
        self.basedir = os.path.abspath('C:\\Users\\Asus\\Videos\\')
        self.cwd = self.basedir
        #self.datasock_timeout = 60  # TODO 
        self.authenticated_users = {'user1': 'password1', 'user2': 'password2'}
        self.command_handlers = {
            'LIST'  : self.list,   #to list the names of the files in the current remote directory
            'PWD'   : self.pwd,     #to find out the pathname of the current directory on the remote machine 
            'USER'  : self.user,
            'PASS'  : self.password,
            'TYPE'  : self.type,
            'QUIT'  : self.quit,
            'RETR'  : self.RETR,
            'STRM'  : self.STRM,
            'HELP'  : self.HELP,
            # 'STOR'  : self.store,
            # 'CWD'   : self.change_dir,
            # 'REST'  : self.REST,
            'PASV'  : self.passive_mode,
            'PORT'  : self.PORT
        }

        self.streaming_types = {
            0 : 'FILE'     ,
            1 : 'LIVE'     ,
            2 : 'WATCH'    ,
            3 : 'LIVE FILE'
        }
        self.frame_index = 0
        threading.Thread.__init__(self)
        Console.log(f'Got connection From {addr}', 'success')
        self.conn.send(('200 Welcome!'+CRLF).encode(self.encoding))

    def run(self):
        while self.conn:
            try:
                req = self.conn.recv(256)
                try:
                    cmd, data = self._get_attributes(req.decode())
                    Console.log(f'recieved info {cmd,data}','info')
                    if cmd in self.command_handlers:
                        self.command_handlers[cmd](data)
                    else:
                        Console.log('Unknown Command recieved','error')
                        self.conn.send((f'500 Unknown command try `help` to get more information about available commands{CRLF}').encode(self.encoding))
                except socket.error as e:
                    Console.log(str(e),'critical')
                    break
                except Exception as e:
                        Console.log(str(e),'critical')
                        self.conn.send(('502 Command not implemented.' + CRLF).encode(self.encoding))
            except ConnectionResetError:
                Console.log(f'Connection reset by peer {'unknown' if not hasattr(self, 'username') else self.username}','critical')
                break
            except ConnectionAbortedError:
                Console.log(f'Connection Aborted by OS','critical')
                break
            except ConnectionRefusedError:
                Console.log(f'Connection Refused','critical')
                break
    
    def HELP(self, data = None):
        help = """
Usage: [Command] [Arguments]

Description:
General information about available commands

Options:
PWD                         Get Current remote directory
LIST                        get lis of files in current directory
USER [optional | USERNAME]  for login purpose, use PASS command next for login
PASS [PASSWORD]             password for last user command (if successful)
TYPE [optional | I | A ]    get current remote mode , I = binary, A = ascii
PASV                        set remote host into passive mode for data transfer
PORT [ADDRESS]              set a port for data transfer, in active mode
RETR [FILENAME]             download a file
STRM [ARGS]                 for streaming, get more help STRM --help
QUIT                        disconnect from server
STORE                       still in development
CWD                         still in development
REST                        still in development
SEEK                        still in development
"""
                        
        Console.log('Sent help','success')
        self.conn.send(f'{help } {CRLF}'.encode(self.encoding))

    def _get_attributes(self,request:str):
        # Split the request into command and data
        args = request.split()
        cmd = args[0].upper()
        data = args[1:]
        return cmd, data
    
    def list(self, data = None):
        Console.log('opening data connection..')
        self.conn.send(f'150 File status okay, about to open data connection..{CRLF}'.encode(self.encoding))
        if self._start_datasock():
            try:
                file_metadata = ''
                for filename in os.listdir(self.cwd):
                    file_metadata += self.toListItem(os.path.join(self.cwd,filename))
                self.datasock.send((str(file_metadata)+'\n').encode(self.encoding))
                self.conn.send(('226  Closing data connection. Requested file action successful').encode(self.encoding))
                Console.log('Sent file list to client', 'success')
                Console.log('Closing data connection', 'info')
                self._stop_datasock()
            except Exception as e:
                Console.log(e, 'error')
                self.conn.send(('550 - Requested action not taken. File unavailable (for example, file not found, or no access).').encode(self.encoding))
                
        else: 
        # except Exception as e:
            Console.log('data socket not Opened','warning')

    
    def toListItem(self,fn:str):
        st = os.stat(fn)
        fullmode='rwxrwxrwx'
        mode=''
        for i in range(9):
            mode+=((st.st_mode>>(8-i))&1) and fullmode[i] or '-'
        d =(os.path.isdir(fn)) and 'd' or '-'
        ftime = time.strftime(' %b %d %H:%M ', time.gmtime(st.st_mtime))
        return str(d+mode+' 1 user group '+str(st.st_size)+ftime+os.path.basename(fn)+'\n')

    def pwd(self, data = None):
        response = self.cwd
        self.conn.send(('257 "%s"%s' % (response, CRLF)).encode(self.encoding))
        Console.log('Sent current working directory to client', 'success')
    
    def quit(self, data = None):
        self.conn.send((f'221 Goodbye.{CRLF}').encode(self.encoding))
        Console.log(f'User {'unknown' if not hasattr(self, 'username') or self.username == 'anonymous' else self.username} closed connection')
        self._close()


    def type(self,data = None):
        if not data:
            self.conn.send((f'200 OK , {self.mode}{CRLF}').encode(self.encoding))
            return
        data = data[0].upper().strip()  # Convert command parameter to uppercase
        if data == 'A' and self.mode == 'I':
            self.mode = 'A'
            self.conn.send((f'200 OK , switched to ASCII{CRLF}').encode(self.encoding))
            Console.log('Switching to ASCII mode.','success')
        elif data == 'I' and self.mode == 'A':
            self.mode = 'I'
            self.conn.send((f'200 OK , switched to Binary{CRLF}').encode(self.encoding))
            Console.log('Switching to Binary mode.','success')
        elif data == 'I' and self.mode == 'I' or data == 'A' and self.mode == 'A':
            Console.log(f'transfer mode already in {'Binary' if data == 'I' else 'ASCII'}')
        else:
            self.conn.send((f'500 Unknown transfer mode. {CRLF}').encode(self.encoding))
            Console.log('Unknown transfer mode','error')


    def user(self, username = None):
        if not username:
            self.conn.send((f'530 Not logged in.{CRLF}').encode(self.encoding))
        elif username[0] in ["", " ", "-",None]:
            username = "anonymous"
            self.username = username
            self.password()
        elif username[0] in self.authenticated_users:
            self.username = username[0]
            self.conn.send((f'331 User name okay, need password.{CRLF}').encode(self.encoding))
            Console.log('User name okay','success')
        else:
            self.conn.send((f'530 Not logged in.{CRLF}').encode(self.encoding))
            Console.log('Unknown user','error')

    def password(self, password = None):
        # If class has attribute named user (means USER command has been used already if not respond as bad sequence of command)
        # then proceed to check user is anonymous if not then check for password in database

        if hasattr(self, 'username'):
            if self.username == "anonymous":
                self.pswd = 'anonymous@'
                self.authrized = False
                self.conn.send((f'230 User logged in as anonymouse, proceed.{CRLF}').encode(self.encoding))
                Console.log('User logged in as anonymous','success')
            elif password[0] == self.authenticated_users[self.username]:
                self.pswd = password[0]
                self.authrized = True
                self.conn.send((f'230 User logged in, proceed.{CRLF}').encode(self.encoding))
                Console.log('User logged in','success')
            else:
                self.authrized = False
                self.conn.send((f'530 Not logged in.{CRLF}').encode(self.encoding))
                Console.log('Incorrect password','error')
        else:
            self.conn.send((f'503 Bad sequence of commands.{CRLF}').encode(self.encoding))
            Console.log('Incorrect order of command','warning')

    def _start_datasock(self):
        if self.pasv_mode:
            if self.servsock:
                self.datasock, addr = self.servsock.accept()
                Console.log(f'data connection opened at {addr[0]}:{addr[1]}', 'info')
            else :
                self.servsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.servsock.bind((self.dataAddr, self.dataPort))
                self.servsock.listen(1)
                self.datasock, addr = self.servsock.accept()
                Console.log(f'data connection opened at {self.dataAddr}:{self.dataPort}')
            return True
        elif hasattr(self, 'dataAddr') and hasattr(self, 'dataPort'):
            try:
                # Console.log(f'Starting data connection at {self.dataAddr}:{self.dataPort}', 'info')
                self.datasock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                self.datasock.connect((self.dataAddr,self.dataPort))
                Console.log(f'data connection opened at {self.dataAddr, self.dataPort}', 'info')
                return True
            except Exception as e:
                self.conn.send(('425 Cannot open data connection').encode(self.encoding))
                Console.log(str(e),'error')

        else :
            try:
                self.datasock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                self.datasock.bind((self.host, 20))
                self.datasock.listen(5)
                self.datasock, addr = self.datasock.accept()
                
                # self.datasock.connect((self.addr[0],20))
                Console.log(f'data connection opened at {addr[0], 20}', 'info')
                return True
            except Exception as e:    
                self.conn.send('425 Cannot open data connection'.encode(self.encoding))
                Console.log(str(e),'error')
        return False

    def _stop_datasock(self):
        self.datasock.close()
        Console.log('data connection closed')
        if self.pasv_mode:
            self.servsock.close()
            self.servsock = None
    
    def PORT(self, cmd:str):
        if self.pasv_mode:
            if self.servsock :
                self.servsock.close()
            self.pasv_mode = False
        try:
            l=cmd[0].split(',')
            self.dataAddr='.'.join(l[:4])
            self.dataPort=(int(l[4])<<8)+int(l[5])
            self.conn.send(f'200 Get port.{CRLF}'.encode(self.encoding))
            Console.log(f'data address recieved {self.dataAddr}:{self.dataPort}', 'success')
        except Exception:
            self.conn.send(f'501 Syntax error in argument, or address not provided{CRLF}'.encode(self.encoding))
            Console.log(f'Syntax error in argument', 'warning')

    def passive_mode(self, data = None):
        if self.pasv_mode :
            self.conn.send('200 Already in passive mode'.encode(self.encoding))
        else:
            try : 
                #set passive mode to true
                # socket in passive mode
                self.servsock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                if self.addr[0] == 'localhost' or self.addr[0] == '127.0.0.1':
                    self.servsock.bind(('localhost',0))
                else :
                    self.servsock.bind((self.host,0))
                self.servsock.listen(1)
                self.dataAddr, self.dataPort = self.servsock.getsockname()
                Console.log(f'Server state changed to passive, {self.dataAddr, self.dataPort}','info')
                self.conn.send(f'227 Entering Passive Mode {self.dataAddr}:{self.dataPort}{CRLF}'.encode(self.encoding))
                self.pasv_mode = True 
            except Exception as e:
                if hasattr (self, "servsock") :
                    self.servsock.close()
                self.pasv_mode = False
                self.conn.send(f'426  Connection closed.{CRLF}'.encode(self.encoding))
                Console.log(str(e),'error')
            
    def RETR(self, cmd=None):
        """Handles the RETR (retrieve file) command with a streaming approach.

        Args:
            cmd (str, optional): The filename received from the client. Defaults to None.
        """
        if not cmd:
            self.conn.send(f'501 Syntax error in parameters or arguments.{CRLF}'.encode(self.encoding))
            return

        # Construct full file path
        fn = os.path.join(self.cwd, cmd[0])
        try:
            # Open file with appropriate mode
            file_mode = 'rb' if self.mode == 'I' else 'r'
            with open(fn, file_mode) as fi:
                self.conn.send(f'150 File status okay, about to open data connection..{CRLF}'.encode(self.encoding))

                if self._start_datasock():
                    file_size = os.path.getsize(fn)
                    self.datasock.sendall(pack("L", file_size))

                    data = fi.read(1024*1024)
                    while data:
                        self.datasock.sendall(data)
                        data = fi.read(1024*1024)

                    Console.log('Sent file data to client', 'success')
                    # Send success message
                    self.conn.send(f'226 Transfer complete.{CRLF}'.encode(self.encoding))
                else :
                    Console.log('data socket not Opened','warning')
        except FileNotFoundError:
            self.conn.send(f'550 File not found.{CRLF}'.encode(self.encoding))
            Console.log(f'File not found: {fn}', 'error')
        except socket.error as e:
            self.conn.send(f'521 - Data connection error.{CRLF}'.encode(self.encoding))
            Console.log(str(e), 'error')
        except Exception as e:
            self.conn.send(f'550 File transfer error.{CRLF}'.encode(self.encoding))
            Console.log(str(e), 'error')
        finally:
            Console.log('Closing data connection...', 'info')
            self._stop_datasock()

    def get_random_id(self,length=6):
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
    
    def STRM(self,args:str = None): # -f filename # -l -f #-l #-w code
        try :

            if len(args) >= 1:
                i = 0
                stream_type = None
                while i < len(args):
                    arg = args[i]
                    if arg == "--help":
                        help = """
Usage: STRM [options]

Description:
This command is used for streaming purpose.

Options:
-f [FILE]        Specify the file to stream from server to client(You)
-l               To start live streaming using client(your) webcam
-w [CODE]        Specify secret code to watch a stream
-l -f [FILE]     Specify file to live stream
"""
                        
                        Console.log('Sent help','success')
                        self.conn.send(f'{help } {CRLF}'.encode(self.encoding))
                        return
                    elif arg == "-f":
                        if i + 1 < len(args):
                            if stream_type == 'LIVE':
                                stream_type = self.streaming_types[3]
                            stream_type = self.streaming_types[0]
                            filename = args[i + 1]
                            i += 2
                        else:
                            Console.log('Missing filename after "-f"','error')
                            self.conn.send(f'500 Error missing filename. Try `STRM --help` to learn more about syntax{CRLF}'.encode(self.encoding))
                            return
                    elif arg == "-w":
                        if i + 1 < len(args):
                            stream_type = self.streaming_types[2]
                            watch_stream_id = args[i + 1]
                            i += 2
                        else:
                            Console.log("Missing code after '-w'",'error')
                            self.conn.send(f'500 Error missing code. Try `STRM --help` to learn more about syntax{CRLF}'.encode(self.encoding))
                            return
                    elif arg == "-l":
                        stream_type = self.streaming_types[1]
                        i += 1
                    else:
                        Console.log(f'Invalid argument {args[i]}','warning')
                        self.conn.send(f'501 Syntax error in arguments. Try `STRM --help` to learn more about syntax{CRLF}'.encode(self.encoding))
                        return

                

                if stream_type == 'FILE':
                    self.stream_file(filename)
                elif stream_type == 'LIVE':
                    self.live_stream()
                elif stream_type == 'WATCH':
                    self.watch_stream(watch_stream_id)
                elif stream_type == 'LIVE FILE':
                    pass
                else :
                    Console.log('No valid operation available for given args', 'info')
                    self.conn.send(f'504 - Command not implemented for that parameter. Try `STRM --help` to learn more about syntax{CRLF}'.encode(self.encoding))

            else:
                Console.log('No argument Provided', 'warning')
                self.conn.send(f'501 Syntax error in arguments. Try `STRM --help` to learn more about syntax{CRLF}'.encode(self.encoding))
                
        except Exception as e:
            Console.log(str(e),'error')

    def stream_file(self, filename):
        filepath = os.path.join(self.cwd, filename)
        if os.path.exists(filepath):
            self.conn.send(f'150 File status okay, about to open data connection..{CRLF}'.encode(self.encoding))
            if self._start_datasock():
                fstreamer = FileStreamer(self.datasock, filepath, self.get_random_id())
                fstreamer.start()
                fstreamer.join()
                self._stop_datasock()
                # Send success message
                self.conn.send(f'226 Transfer complete.{CRLF}'.encode(self.encoding))
        else:
            self.conn.send(f'550 File not found.{CRLF}'.encode(self.encoding))
            Console.log(f'File `{filename}` Not Found on server', 'error')

    def live_stream(self):
        if self.authrized :
            id = self.get_random_id()
            self.conn.send(f'150 ok, {id}{CRLF}'.encode(self.encoding))
            if self._start_datasock():
                Console.log('Reading Live Streams')
                Console.log(f'streaming id for user {self.clientID} : {id}')
                lstreamer = LiveStreamer(self.datasock, self.frames, id)
                lstreamer.start()
                lstreamer.join()
                self._stop_datasock()
                self.conn.send(f'226 Transfer complete.{CRLF}'.encode(self.encoding))
                Console.log('Stream finished')
                del self.frames[id]
        else:
            Console.log(f'Not Logged In')
            self.conn.send(f'530 Not logged in.{CRLF}'.encode(self.encoding))

    def watch_stream(self, id:str ):
        if id in self.frames.keys():
            Console.log('Sending LIve Stream')
            self.conn.send(f'150 okay, about to open data connection..{CRLF}'.encode(self.encoding))
            if self._start_datasock():
                while True:
                        frame : collections.deque= self.frames.get(id, "404")
                        if frame == "404":
                            break
                        try:
                            self.datasock.sendall(frame[0])
                        except ConnectionError:
                            break


                        # media : list = self.frames.get(id, "404")
                        # if media == "404":
                        #     Console.log('Media ie Audio and Video frames empty')
                        #     break
                        # print(len(media[0]))
                        # try:
                        #     self.datasock.sendall(media[0][0]+media[1][0])
                        # except:
                        #     break

                self._stop_datasock()
                self.conn.send(f'226 Transfer complete.{CRLF}'.encode(self.encoding))
        else :
            Console.log(f'ID [{id}] not found')
            self.conn.send(f'504 error,stream ID not Found.{CRLF}'.encode(self.encoding))



    def _close(self):
        conn = self.conn
        self.conn.close()
        self.conn = None
        if conn is not None:
            conn.close()
