import socket
import pickle
import queue
import struct,collections
import cv2,numpy as np
import threading,pyaudio,time
from datetime import timedelta

class VideoPlayer(threading.Thread):
    def __init__(self, data_socket:socket.socket,filename = None):
        threading.Thread.__init__(self)
        self.client_socket = data_socket
        self.playing = True
        self.frame_index = 0
        self.frame_buffer = collections.deque(maxlen=1500)
        self.audio_buffer = collections.deque()
        self.video_thread = threading.Thread(target=self.play_video)
        self.audio_thread = threading.Thread(target=self.play_audio)
        self.video_thread.daemon = True
        self.audio_thread.daemon = True
        self.finished = False
        self.has_audio = False

    def run(self):
        print("Connected to server")
        self.__get_metadata__() #information of file

        self.video_thread.start()
        if self.has_audio:
            self.audio_thread.start()
        self.receive_frames()
        self.video_thread.join()
        if self.has_audio:
            self.audio_thread.join()
        self.quit()

    def __get_metadata__(self):
        metadata = self.client_socket.recv(512)
        self.meta:dict = pickle.loads(metadata) # decode meta data
        self.filename = self.meta['file']['filename']
        self.duration = self.meta['file']['duration']
        self.fps = self.meta['video']['fps']
        self.fps_ms = int(1000/self.fps)
        if 'audio' in self.meta.keys():
            self.has_audio = True
            channels = self.meta['audio']['channels']
            sample_rate = self.meta['audio']['sample_rate']
            self.p = pyaudio.PyAudio()
            self.audio_stream = self.p.open(format=pyaudio.paFloat32,
                channels=channels,rate=sample_rate,output=True)


    def receive_frames(self):
        # rec = 0
        while True:
            try:
                if self.finished:
                    break
                if self.has_audio:
                    audio_size_data = self.client_socket.recv(4)
                    if not audio_size_data:
                        break
                    audio_size = struct.unpack('L', audio_size_data)[0]
                    audio_data = b''
                    while len(audio_data) < audio_size:
                        chunk = self.client_socket.recv(audio_size - len(audio_data))
                        if not chunk:
                            break
                        audio_data += chunk
                    audio_frames = pickle.loads(audio_data)
                    self.audio_buffer.extend(audio_frames)

                # Receive the frames length
                frames_length_data = self.client_socket.recv(struct.calcsize("L"))
                if not frames_length_data:
                    break

                #decode length
                frames_length = struct.unpack("L", frames_length_data)[0]
                if frames_length == 0:
                    self.finished = True
                    break

                frames_data = b""
                while len(frames_data) < frames_length:
                    remaining_data = frames_length - len(frames_data)
                    try:
                        frames_data += self.client_socket.recv(remaining_data)
                    except socket.error:
                        continue

                # Deserialize the frames using pickle
                frames = pickle.loads(frames_data)
                self.frame_buffer.extend(frames)
                    
            except Exception:
                continue

    def play_video(self):
        while True:
            if self.playing:
                if self.has_audio:
                    if self.frame_buffer and self.audio_buffer:

                        frames = self.frame_buffer.copy()
                        self.frame_buffer.clear()
                        cv2.namedWindow('V')
                        while True:
                            try:
                                current_total_seconds = int(self.frame_index/self.fps)
                                cv2.imshow('V', frames.popleft())
                                cv2.setWindowTitle('V', f'{self.filename}    |    {timedelta(seconds=current_total_seconds)}')
                                self.frame_index += 1
                                key = cv2.waitKey(self.fps_ms)
                                if key & 0xFF == ord('q'):
                                    self.finished =True
                                    # self.quit()
                                    break
                                elif key & 0xFF == ord(' '):
                                    print('paused')
                                    self.pause()
                                    break
                                
                            except:
                                break
                        # self.frame_buffer = self.frame_buffer[500:]
                        # frames.clear()
                    else:
                        if self.finished : break
                        else : continue
                else:
                    if self.frame_buffer and not self.finished:
                        while True:
                            try:
                                current_total_seconds = int(self.frame_index/self.fps)
                                cv2.imshow('V', frames.popleft())
                                cv2.setWindowTitle('V', f'{self.filename}    |    {timedelta(seconds=current_total_seconds)}')
                                self.frame_index += 1
                                key = cv2.waitKey(self.fps_ms)
                                if key & 0xFF == ord('q'):
                                    self.finished = True
                                    self.quit()
                                    break
                                elif key & 0xFF == ord(' '):
                                    print('paused')
                                    self.pause()
                                    break
                                
                            except:
                                break
                        # self.frame_buffer = self.frame_buffer[500:]
                        # frames.clear()
                    else:
                        if self.finished : break
                        else : continue
            elif self.finished: break
            else : self.click_handler()

    def play_audio(self):
        while True:
            if self.audio_buffer and self.frame_buffer:
                # print('right ig')
                if self.playing:
                    frames = self.audio_buffer.copy()
                    self.audio_buffer.clear()
                    for frame in frames:
                        # Write the audio bytes to the stream
                        self.audio_stream.write(frame.tobytes())
                        if not self.playing:
                            self.pause()
                    frames.clear()
                    # while True:
                    #     try:
                    #         self.audio_stream.write(frames.popleft().tobytes())
                    #         if not self.playing:
                    #             self.pause()
                    #     except:
                    #         break       
            else:
                if self.finished : break
                else : continue

    def play(self):
        self.playing = True
        if self.has_audio:
            self.audio_stream.start_stream()

    def pause(self):

        self.playing = False
        if self.has_audio:
            self.audio_stream.stop_stream()
        self.click_handler()

    def click_handler(self):
        key = cv2.waitKey(0)
        print('waiting for key press')
        if key & 0xFF == ord('q'):
            self.quit()
        elif key & 0xFF == ord(' '):
            print('pressed space')
            self.play()
            
            
    
    def quit(self):
        self.playing = False
        self.finished = True
        self.frame_buffer.clear()
        self.audio_buffer.clear()
        if self.has_audio:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.p.terminate()
        cv2.destroyAllWindows()
        self.client_socket.close()




class LiveStreamer(threading.Thread):
    def __init__(self, data_socket:socket.socket) -> None:
        self.data_conn = data_socket
        self.finished = False
        BUFFER_SIZE = 10

        self.frame_buffer = collections.deque(maxlen=BUFFER_SIZE)
        self.audio_buffer = collections.deque(maxlen=BUFFER_SIZE)
        self.video_thread = threading.Thread(target=self.play_video)
        self.send_thread = threading.Thread(target=self.send_data)
        self.audio_thread = threading.Thread(target=self.capture_audio)
        # self.audio_thread = threading.Thread(target=self.play_audio)
        threading.Thread.__init__(self)

    def send_data(self):
        while True:
            try:
                if len(self.frame_buffer) > 0 and len(self.audio_buffer) > 0:
                    v_frame = self.frame_buffer.popleft()
                    v_frame_data = v_frame.tobytes()
                    v_frame_size = len(v_frame_data)
                    # Send frame size and frame data over the connection
                    self.data_conn.sendall(struct.pack("L", v_frame_size) + v_frame_data)

                    # a_frame = self.audio_buffer.popleft()
                    # a_frame_size = len(a_frame)
                    # self.data_conn.sendall(struct.pack("L", a_frame_size) + a_frame)
                else:
                    if self.finished: break
            except:
                break

    def play_video(self):
        cap = cv2.VideoCapture(0)
        cv2.namedWindow('W')
        ct = time.time()
        while True:
            ret, frame = cap.read()
            if ret:
                self.frame_buffer.append(frame)
                st = time.time()
                ts = st-ct
                cv2.imshow('W', frame)
                cv2.setWindowTitle('W', f'Live  |  {timedelta(seconds=ts)}')
                if cv2.waitKey(16) & 0xFF == ord('q'):
                    self.finished = True
                    break
        cap.release()
        cv2.destroyAllWindows()
        self.data_conn.close()

    def capture_audio(self):
        #-------Audio-------
        FORMAT = pyaudio.paInt32 # 16-bit PCM
        CHANNELS = 1              # Mono
        RATE = 44100              # Sampling rate (samples per second)
        CHUNK = 1024              # Number of frames per buffer
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
        while True:
            frame = stream.read(CHUNK)
            self.audio_buffer.append(frame)
            if self.finished: break
        stream.stop_stream()
        stream.close()
        audio.terminate()
        print('adclosed')

    def run(self):
        print('Preparing Live Stream...')
        self.send_thread.daemon = True
        self.video_thread.start()
        self.send_thread.start()
        self.video_thread.join()
        self.send_thread.join()



class WatchStream(threading.Thread):
    def __init__(self, data_socket:socket.socket) -> None:
        self.data_conn = data_socket
        self.finished = False
        BUFFER_SIZE = 100
        self.frame_buffer = collections.deque(maxlen=BUFFER_SIZE)
        self.audio_buffer = collections.deque(maxlen=BUFFER_SIZE)
        self.video_thread = threading.Thread(target=self.play_video)
        self.audio_thread = threading.Thread(target=self.play_audio)
        self.get_thread = threading.Thread(target=self.get_data)
        # self.frame_buffer = collections.deque(maxlen=1500)
        threading.Thread.__init__(self)

    def get_data(self):
        while True:
            try:
                print('hmm')
                frames_length_data = self.data_conn.recv(4)
                if not frames_length_data:
                    break

                #decode length
                frames_length = struct.unpack("L", frames_length_data)[0]
                if frames_length == 0:
                    self.finished = True
                    break
                frames_data = b""
                while len(frames_data) < frames_length:
                    remaining_data = frames_length - len(frames_data)
                    try:
                        frames_data += self.data_conn.recv(remaining_data)
                    except socket.error:
                        continue
                # Convert frame data to numpy array
                frame = np.frombuffer(frames_data, dtype=np.uint8).reshape((480, 640, 3))
                self.frame_buffer.append(frame)


                # Audio
                # a_frame_size_data = self.data_conn.recv(4)
                # if not a_frame_size_data:
                #     break
                # a_frame_size = struct.unpack('L', a_frame_size_data)[0]

                # a_frame_data = b''
                # while len(a_frame_data) < a_frame_size:
                #     chunk = self.data_conn.recv(a_frame_size - len(a_frame_data))
                #     if not chunk:
                #         break  # If no more data received, break out of the loop
                #     a_frame_data += chunk
                # self.audio_buffer.append(a_frame_data)
            except:
                break

    def play_audio(self):
        #-------Audio-------
        FORMAT = pyaudio.paInt32 # 16-bit PCM
        CHANNELS = 1              # Mono
        RATE = 44100              # Sampling rate (samples per second)
        CHUNK = 1024              # Number of frames per buffer
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
        
        while True:
            if len(self.audio_buffer) > 0:
                stream.write(self.audio_buffer.popleft())
                if self.finished: break


    def play_video(self):
        cv2.namedWindow('W')
        ct = time.time()
        while True:
            try:
                if len(self.frame_buffer) > 0:
                    frame = self.frame_buffer.popleft()
                    st = time.time()
                    ts = st-ct
                    cv2.imshow('W', frame)
                    cv2.setWindowTitle('W', f'Live  |  {timedelta(seconds=ts)}')
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            except:
                self.finished = True
                break
        cv2.destroyAllWindows()
        self.data_conn.close()

    def run(self):
        print('Preparing To watch Stream...')
        self.video_thread.daemon = True
        self.get_thread.start()
        self.video_thread.start()
        # self.audio_thread.start()
        self.get_thread.join()
        self.video_thread.join()
        # self.audio_thread.join()


