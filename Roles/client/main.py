import base64
import commands
import cv2
import importlib
import json
import math
#import numpy as np
#from operator import itemgetter
import os
import Queue
import random
import settings 
import serial
import sys
#import subprocess
import threading
import time
import traceback
import subprocess
from pydub import AudioSegment
from glob import glob

from thirtybirds_2_0.Network.manager import init as thirtybirds_network
from thirtybirds_2_0.Adaptors.Cameras.c920 import init as camera_init
from thirtybirds_2_0.Updates.manager import init as updates_init

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
UPPER_PATH = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]
DEVICES_PATH = "%s/Hosts/" % (BASE_PATH )
THIRTYBIRDS_PATH = "%s/thirtybirds_2_0" % (UPPER_PATH )

sys.path.append(BASE_PATH)
sys.path.append(UPPER_PATH)

########################
## IMAGES
########################

class Images(object):
    def __init__(self, capture_path):
        self.capture_path = capture_path
        self.camera = camera_init(self.capture_path)
    def capture_image(self, filename):
        self.camera.take_capture(filename)
    def get_capture_filenames(self):
        return [ filename for filename in os.listdir(self.capture_path) if filename.endswith(".png") ]
    def delete_captures(self):
        previous_filenames = self.get_capture_filenames()
        for previous_filename in previous_filenames:
            os.remove("{}{}".format(self.capture_path,  previous_filename))
    def get_capture_filepaths(self):
        filenames = self.get_capture_filenames()
        return list(map((lambda filename:  os.path.join(self.capture_path, filename)), filenames))
    def get_image_as_base64(self, filename):
        pathname = "{}{}".format(self.capture_path, filename)
        with open(pathname, "rb") as image_file:
            return base64.b64encode(image_file.read())


########################
## SPEECH
########################

class Speaker():
    def __init__(self):
        pass

    def number_to_audio_files(self, number):
        out = []
        number = str(number)
        number = number.replace('0.', '')
        for digit in number:
            out.append(BASE_PATH + '/audio/' + digit + '.wav')
        return out


    def speak(self, generation, iteration, fitness):
        generation_files = self.number_to_audio_files(generation)
        iteration_files = self.number_to_audio_files(iteration)
        fitness_files = self.number_to_audio_files(fitness)

        print generation, iteration
        print generation_files
        print iteration_files

        all_audio = []
        all_audio = [BASE_PATH + '/audio/generation.wav']
        all_audio += generation_files
        all_audio += [BASE_PATH + '/audio/iteration.wav']
        all_audio += iteration_files

        # all_audio += fitness_files

        for audio_file in all_audio:
            subprocess.call(['omxplayer', audio_file])

class Speech(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.queue = Queue.Queue()

    def add_to_queue(self, topic, msg):
        self.queue.put((topic, msg))

    def number_to_audio_files(self, number):
        out = []
        number = str(number)
        number = number.replace('0.', '')
        for digit in number:
            out.append(BASE_PATH + '/audio/numbers/' + digit + '.wav')
        return out

    def say(self, generation, iteration):
        nouns = glob(BASE_PATH + "/audio/nouns/*.wav")
        verbs = glob(BASE_PATH + "/audio/verbs/*.wav")
        generation_files = self.number_to_audio_files(generation)
        iteration_files = self.number_to_audio_files(iteration)

        phrase = []
        phrase += [random.choice(glob(BASE_PATH + '/audio/generations/*.wav'))]
        phrase += generation_files
        phrase += [1000]
        phrase += [random.choice(glob(BASE_PATH + '/audio/iterations/*.wav'))]
        phrase += iteration_files
        phrase += [1000]
        phrase += [random.choice(verbs), random.choice(verbs), random.choice(nouns)]

        print(phrase)

        out = AudioSegment.silent()
        for i, p in enumerate(phrase):
            print(p)
            if type(p) == type(1):
                p = AudioSegment.silent(duration=p)
            else:
                p = AudioSegment.from_wav(p)
            if i > 0:
                crossfade = 100
            else:
                crossfade = 50
            p = p.normalize()
            out = out.append(p, crossfade=crossfade)

        out.export("audio.mp3", format="mp3", parameters=["-ac", "2", "-vol", "250"])
        subprocess.call(["omxplayer", "audio.mp3"])


    def run(self):
        while True:
            topic, msg = self.queue.get(True)
            if topic == "local/speech/say":
                generation, iteration, fitness = msg
                self.say(generation, iteration)
                # generation_files = self.number_to_audio_files(generation)
                # iteration_files = self.number_to_audio_files(iteration)
                # fitness_files = self.number_to_audio_files(fitness)
                #
                # all_audio = []
                # all_audio = [BASE_PATH + '/audio/generation.wav']
                # all_audio += generation_files
                # all_audio += [BASE_PATH + '/audio/iteration.wav']
                # all_audio += iteration_files
                #
                # # all_audio += fitness_files
                #
                # for audio_file in all_audio:
                #     subprocess.call(['omxplayer', audio_file])


########################
## DRIPPERS
########################
class Dripper(threading.Thread):
    def __init__(self, dripper_id, dmx, active=False):
        threading.Thread.__init__(self)
        self.dripper_id = dripper_id
        self.dmx = dmx
        self.initial_delay = random.randint(0, 4)
        self.reset(active)

    def reset(self, active):
        self.active = active
        self.ontime = random.uniform(0.1, 0.2)
        self.offtime = random.uniform(1.0, 1.5)
        self.stop_drip()

    def start_drip(self):
        self.dmx.add_to_queue("local/env_state/set", {self.dripper_id: 255})

    def stop_drip(self):
        self.dmx.add_to_queue("local/env_state/set", {self.dripper_id: 0})

    def run(self):
        time.sleep(self.initial_delay)
        while True:
            if self.active:
                # print self.dripper_id, "on"
                self.start_drip()
                time.sleep(self.ontime)
                # print self.dripper_id, "off"
                self.stop_drip()
                time.sleep(self.offtime)

########################
## DMX
########################

class DMX(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.queue = Queue.Queue()
        self.ser = serial.Serial()
        self.ser.port = '/dev/ttyUSB0'
        if self.ser.isOpen():
            self.ser.close()
        print ('Opening Enttec USB DMX Pro on', self.ser.port, 'at', self.ser.baudrate, 'baud')
        self.ser.open()

        # if you add or modify DMX channels, adjust below!
        self.device_states = [0]*40
        self.name_to_address_map = {
            # "mister_1": 0,
            # "mister_2": 1,
            # "pump": 2,
            # "grow_light": 3,
            # "dj_light_2_d": 7,
            # "dj_light_2_r": 8,
            # "dj_light_2_g": 9,
            # "dj_light_2_b": 10,
            # "dj_light_1_d": 14,
            # "dj_light_1_r": 15,
            # "dj_light_1_g": 16,
            # "dj_light_1_b": 17,
            # "raindrops_1": 31,
            # "raindrops_2": 32,
            # "raindrops_3": 33,
            "mister_1": 1,
            "mister_2": 2,
            "fan": 3,
            "dj_light_2_d": 8,
            "dj_light_2_r": 9,
            "dj_light_2_g": 10,
            "dj_light_2_b": 11,
            "dj_light_1_d": 15,
            "dj_light_1_r": 16,
            "dj_light_1_g": 17,
            "dj_light_1_b": 18,
            "dj_light_3_d": 27,
            "dj_light_3_r": 28,
            "dj_light_3_g": 29,
            "dj_light_3_b": 30,
            "raindrops_1": 32,
            "raindrops_2": 33,
            "raindrops_3": 34,
        }
    def convert_to_DMX_addresses(self, data):
        values_for_dmx = {}
        for device_name,dmx_val in data.items():
            values_for_dmx[str(self.name_to_address_map[device_name])] = dmx_val
        return values_for_dmx

    def sendmsg(self, label, message=[]):
        # How many data points to send
        l = len(message)
        lm = l >> 8
        ll = l - (lm << 8)
        if l <= 600:
            if self.ser.isOpen():
                # Create the array to write to the serial port
                arr = [0x7E, label, ll, lm] + message + [0xE7]
                # Convert to byte array and write it
                self.ser.write(bytearray(arr))
        else:
            # Too long!
            sys.stderr.write('TX_ERROR: Malformed message! The message to be send is too long!\n')

    def add_to_queue(self, topic, msg):
        self.queue.put((topic, msg))

    def run(self):
        toggle = False
        while True:
            topic, msg = self.queue.get(True)
            if topic == "local/env_state/set":
                dmx_address_to_value_map = self.convert_to_DMX_addresses(msg)
                print dmx_address_to_value_map
                for address, value in dmx_address_to_value_map.items():
                    self.device_states[int(address)] = int(value)
                self.sendmsg(6, self.device_states)


########################
## NETWORK
########################

class Network(object):
    def __init__(self, hostname, network_message_handler, network_status_handler):
        self.hostname = hostname
        self.thirtybirds = thirtybirds_network(
            hostname=hostname,
            role="client",
            discovery_multicastGroup=settings.discovery_multicastGroup,
            discovery_multicastPort=settings.discovery_multicastPort,
            discovery_responsePort=settings.discovery_responsePort,
            pubsub_pubPort=settings.pubsub_pubPort,
            message_callback=network_message_handler,
            status_callback=network_status_handler
        )

########################
## MAIN
########################

class Main(threading.Thread):
    def __init__(self, hostname):
        threading.Thread.__init__(self)
        self.hostname = hostname
        self.capture_path = "/home/pi/wetlands/captures/"
        self.queue = Queue.Queue()
        self.network = Network(hostname, self.network_message_handler, self.network_status_handler)
        #self.utils = Utils(hostname)
        self.images = Images(self.capture_path)
        self.dmx = DMX()
        self.dmx.daemon = True
        self.dmx.start()

        self.speech = Speech()
        self.speech.daemon = True
        self.speech.start()

        # self.speech = Speaker()

        # self.drippers = []
        # for dripper_name in ["raindrops_1", "raindrops_2", "raindrops_3"]:
        #     dripper = Dripper(dripper_name, self.dmx)
        #     dripper.daemon = True
        #     dripper.start()
        #     self.drippers.append(dripper)

        #self.network.thirtybirds.subscribe_to_topic("reboot")
        #self.network.thirtybirds.subscribe_to_topic("remote_update")
        #self.network.thirtybirds.subscribe_to_topic("remote_update_scripts")
        self.network.thirtybirds.subscribe_to_topic(self.hostname)
        self.network.thirtybirds.subscribe_to_topic("wetlands-environment-all/")

    def network_message_handler(self, topic_msg):
        # this method runs in the thread of the caller, not the tread of Main

        topic, msg =  topic_msg # separating just to eval msg.  best to do it early.  it should be done in TB.
        if topic not in  ["client_monitor_request"]:
            print "Main.network_message_handler", topic_msg
        if len(msg) > 0: 
            msg = eval(msg)
        self.add_to_queue(topic, msg)

    def network_status_handler(self, topic_msg):
        # this method runs in the thread of the caller, not the tread of Main
        print "Main.network_status_handler", topic_msg

    def override(self, msg):
        overrides = {
            "wetlands-environment-1": {
                "dj_light_3_g": 0
            },
            "wetlands-environment-2": {
                "dj_light_3_b": 0,
                "dj_light_2_g": 0,
            }
        }

        for key in overrides[self.hostname]:
            msg[key] = overrides[self.hostname][key]

        return msg

    def add_to_queue(self, topic, msg):
        self.queue.put((topic, msg))

    def run(self):
        while True:
            try:
                topic, msg = self.queue.get(True)

                if topic == "{}/image_capture/request".format(self.hostname):
                    self.images.delete_captures()
                    filename = "{}{}".format(self.hostname, ".png")
                    self.images.capture_image(filename)
                    image_as_string = self.images.get_image_as_base64(filename)
                    self.network.thirtybirds.send("controller/image_capture/response", (self.hostname,image_as_string))

                if topic == "{}/env_state/set".format(self.hostname):
                    # for dripper in self.drippers:
                    #     di = dripper.dripper_id
                    #     if di in msg:
                    #         dripper.reset(msg[di] == 255)
                    #         msg[di] = 0
                    msg = self.override(msg)
                    self.dmx.add_to_queue("local/env_state/set", msg)

                if topic == "{}/speech/say".format(self.hostname):
                    self.speech.add_to_queue("local/speech/say", msg)
                    # g, i, f = msg
                    # self.speech.speak(g, i, f)

            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print e, repr(traceback.format_exception(exc_type, exc_value,exc_traceback))

########################
## INIT
########################

def init(HOSTNAME):
    main = Main(HOSTNAME)
    main.daemon = True
    main.start()
    return main
