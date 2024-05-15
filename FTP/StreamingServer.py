import socket
import pickle
import struct
from log import Console
import moviepy.editor as mp
import cv2
import ffmpeg
import time,threading,collections
import os, numpy as np




class FileStreamer(threading.Thread):

    def __init__(self, data_socket:socket.socket, filepath :str, id:str) -> None:
        self.id = id
        self.data_conn = data_socket
        self.filepath = filepath
        self.hasaudio = True

        threading.Thread.__init__(self)

    def __get_file_data__(self):
        metadata = ffmpeg.probe(self.filepath)
        f = metadata['streams'][0]['avg_frame_rate'].split('/')

        self.frame_width = int(metadata['streams'][0]['width'])
        self.frame_height = int(metadata['streams'][0]['height'])
        if 'display_aspect_ratio' not in metadata['streams'][0].keys():
            self.aspect_ratio = self.frame_width/self.frame_height
        else:
            args = metadata['streams'][0]['display_aspect_ratio'].split(':')
            self.aspect_ratio = int(args[0])/int(args[1])

        self.fps = int(f[0])//int(f[1])
        if len(metadata['streams']) == 1: #no audio
            self.hasaudio = False
            self.meta = {
            'video': {
                'pix_fmt': metadata['streams'][0]['pix_fmt'],
                'width': self.frame_width,
                'height': self.frame_height,
                'aspect_ratio':  self.aspect_ratio,
                'fps': self.fps,
                'bit_rate': int(metadata['streams'][0]['bit_rate'])
            },
            'file': {
                'filename': os.path.basename((metadata['format']['filename'])),
                'duration': float(metadata['format']['duration']),
                'format_name': metadata['format']['format_name']
            }
        }
        else :
            self.audio_sample_rate = int(metadata['streams'][1]['sample_rate'])
            self.audio_channels = int(metadata['streams'][1]['channels'])
            self.audio_bitrate = int(metadata['streams'][1]['bit_rate'])
            self.meta = {
                'video': {
                    'pix_fmt': metadata['streams'][0]['pix_fmt'],
                    'width': self.frame_width,
                    'height': self.frame_height,
                    'aspect_ratio': self.aspect_ratio,
                    'fps': self.fps,
                    'bit_rate': int(metadata['streams'][0]['bit_rate'])
                },
                'audio': {
                    'sample_rate': self.audio_sample_rate,
                    'channels': self.audio_channels,
                    'bit_rate': self.audio_bitrate
                },
                'file': {
                    'filename': os.path.basename((metadata['format']['filename'])),
                    'duration': float(metadata['format']['duration']),
                    'format_name': metadata['format']['format_name']
                }
            }
        

    def resize(self,frame):
        if self.frame_width > 1920 or self.frame_height > 1080:
        # Aspect ratio of 1080p
            target_width = 1920
            target_height = 1080
            target_aspect_ratio = target_width / target_height

            # Current aspect ratio
            current_aspect_ratio = self.aspect_ratio

            if current_aspect_ratio > target_aspect_ratio:
                new_width = target_width
                new_height = int(new_width / current_aspect_ratio)

            else:
                new_height = target_height
                new_width = int(new_height * current_aspect_ratio)

            return cv2.resize(frame,(new_width, new_height))
        else:
            return frame


    def run(self):
        Console.log('Preparing File to Stream...', 'info')
        self.__get_file_data__()
        cap = cv2.VideoCapture(self.filepath)
        if self.hasaudio:
            audio = mp.AudioFileClip(self.filepath)

        VIDEO_BUFFER_SIZE =  self.fps*10
        if self.hasaudio:
            AUDIO_BUFFER_SIZE =  self.audio_sample_rate *10
        SEND_INTERVAL = 0.0

        pickled_meta = pickle.dumps(self.meta)
        self.data_conn.sendall(pickled_meta)
        frame_index = 0
        frame_buffer = collections.deque()
        audio_buffer = collections.deque()
        

        if self.hasaudio:
            for aframe in audio.iter_frames():
                audio_buffer.append(aframe.astype(np.float32))

                if len(audio_buffer) == AUDIO_BUFFER_SIZE:
                    for _ in range(VIDEO_BUFFER_SIZE):
                        ret, frame = cap.read()
                        if not ret:
                            break
                        rframe = self.resize(frame)
                        frame_buffer.append(rframe)
                    try : 
                        serialized_audio_buffer = pickle.dumps(audio_buffer)
                        audio_buffer_length =len(serialized_audio_buffer)
                        self.data_conn.sendall(struct.pack("L", audio_buffer_length))
                        self.data_conn.sendall(serialized_audio_buffer)
                        audio_buffer.clear()

                        if len(frame_buffer) == 0:
                            frame_buffer_length = 0
                            self.data_conn.sendall(struct.pack("L", frame_buffer_length))
                            break

                        serialized_frame_buffer = pickle.dumps(frame_buffer)
                        frame_buffer_length = len(serialized_frame_buffer)
                        self.data_conn.sendall(struct.pack("L", frame_buffer_length))
                        self.data_conn.sendall(serialized_frame_buffer)
                        frame_buffer.clear()

                        time.sleep(SEND_INTERVAL)
                    except ConnectionResetError:
                        break
        else:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                rframe = self.resize(frame)
                frame_buffer.append(rframe)

                if( len(frame_buffer) == VIDEO_BUFFER_SIZE):
                    serialized_frame_buffer = pickle.dumps(frame_buffer)
                    frame_buffer_length = len(serialized_frame_buffer)
                    self.data_conn.sendall(struct.pack("L", frame_buffer_length))
                    self.data_conn.sendall(serialized_frame_buffer)
                    frame_buffer.clear()

        frame_buffer.clear()
        audio_buffer.clear()


class LiveStreamer(threading.Thread):
    def __init__(self, data_socket:socket.socket, streams:dict, id) -> None:
        self.datasock = data_socket
        self.streams = streams
        self.id = id
        BUFFER_SIZE = 10
        # self.media:list = []
        self.frame_buffer = collections.deque(maxlen=BUFFER_SIZE)
        self.audio_buffer = collections.deque(maxlen=BUFFER_SIZE)
        # self.media.append(self.frame_buffer)
        # self.media.append(self.audio_buffer)
        self.streams[id] = self.frame_buffer
        # self.streams[id] = self.media
        threading.Thread.__init__(self)

    def run(self):
        while True:
            try:
                #Recieve Video Frame size
                frame_size_data = self.datasock.recv(4)
                if not frame_size_data:
                    break
                frame_size = struct.unpack('L', frame_size_data)[0]
                if frame_size ==0:
                    break
                frame_data = b''
                while len(frame_data) < frame_size:
                    chunk = self.datasock.recv(min(frame_size - len(frame_data), 4096))
                    if not chunk:
                        break
                    frame_data += chunk
                self.frame_buffer.append(struct.pack("L", frame_size) + frame_data)

                # Receive Audio frame size
                # a_frame_size_data = self.datasock.recv(4)
                # if not a_frame_size_data:
                #     break
                # a_frame_size = struct.unpack('L', a_frame_size_data)[0]
                # print(a_frame_size)
                # a_frame_data = b''
                # while len(a_frame_data) < a_frame_size:
                #     chunk = self.datasock.recv(a_frame_size - len(a_frame_data))
                #     if not chunk:
                #         break  # If no more data received, break out of the loop
                #     a_frame_data += chunk
                # self.audio_buffer.append(struct.pack('L', a_frame_size)+a_frame_data)
                
            except:
                break

