#!/usr/bin/env python3

import pygame
from pygame.locals import *
import pygame, pygame.font, pygame.event, pygame.draw, string
from matplotlib import cm
import numpy as np
from scipy import signal

import sys
if sys.version_info > (3,):
    buffer = memoryview
    def bytearray2str(b):
        return b.decode('ascii')
else:
    def bytearray2str(b):
        return str(b)

import random
import array
import socket
import time
from datetime import datetime
from collections import deque

from kiwi import wsclient
import mod_pywebsocket.common
from mod_pywebsocket.stream import Stream
from mod_pywebsocket.stream import StreamOptions

from optparse import OptionParser

# predefined RGB colors
GREY = (200,200,200)
WHITE = (255,255,255)
BLACK = (0,0,0)
D_GREY = (50,50,50)
D_RED = (200,0,0)
D_BLUE = (0,0,200)
D_GREEN = (0,200,0)
RED = (255,0,0)
BLUE = (0,0,255)
GREEN = (0,255,0)

allowed_sym = [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]
allowed_sym += [K_BACKSPACE, K_RETURN, K_ESCAPE]

HELP_MESSAGE_LIST = ["COMMANDS HELP",
        "",
        "- LEFT/RIGHT: move freq +/- 1kHz (+SHIFT: X10)",
        "- PAGE UP/DOWN: move freq +/- 1MHz",
        "- UP/DOWN: zoom in/out by a factor 2X",
        "- U/L/C: switches to USB, LSB, CW",
        "- F: enter frequency with keyboard",
        "- H: displays this help window",
        "- SHIFT+ESC: quits",
        "",
        "",
        "   --- 73 de marco/IS0KYB ---   "]


def process_audio_stream():
    data = snd_stream.receive_message()
    #samples = np.zeros((1024))
    if bytearray2str(data[0:3]) == "SND": # this is one waterfall line
        data = data[10:]
        count = len(data) // 2
        samples = np.ndarray(count, dtype='>h', buffer=data).astype(np.int16)
        return samples


def display_box(screen, message):
    fontobject = pygame.font.SysFont('Mono',12)

    pygame.draw.rect(screen, BLACK,
                   ((screen.get_width() / 2) - 100,
                    (screen.get_height() / 2) - 10,
                    200,20), 0)
    pygame.draw.rect(screen, WHITE,
                   ((screen.get_width() / 2) - 102,
                    (screen.get_height() / 2) - 12,
                    204,24), 1)
    if len(message) != 0:
        screen.blit(fontobject.render(message, 1, WHITE),
                ((screen.get_width() / 2) - 100, (screen.get_height() / 2) - 10))
    pygame.display.flip()

def display_help_box(screen, message_list):
    font_size = 10
    fontobject = pygame.font.SysFont('Mono',font_size)
    window_size = 300
    pygame.draw.rect(screen, (0,0,0),
                   ((screen.get_width() / 2) - window_size/2,
                    (screen.get_height() / 2) - window_size/2,
                    window_size , window_size), 0)
    pygame.draw.rect(screen, (255,255,255),
                   ((screen.get_width() / 2) - window_size/2,
                    (screen.get_height() / 2) - window_size/2,
                    window_size,window_size), 1)

    if len(message_list) != 0:
        for ii, msg in enumerate(message_list):
            screen.blit(fontobject.render(msg, 1, WHITE),
                    (screen.get_width() / 2 - window_size/2 + font_size, 
                    screen.get_height() / 2-window_size/2 + ii*font_size + font_size))
    pygame.display.flip()

def kiwi_zoom_to_span(zoom):
    """return frequency span in kHz for a given zoom level"""
    assert(zoom >=0 and zoom <= MAX_ZOOM)
    return MAX_FREQ/2**zoom

def kiwi_start_frequency_to_counter(start_frequency_):
    """convert a given start frequency in kHz to the counter value used in _set_zoom_start"""
    assert(start_frequency_ >= 0 and start_frequency_ <= MAX_FREQ)
    counter = round(start_frequency_/MAX_FREQ * 2**MAX_ZOOM * WF_BINS)
    start_frequency_ = counter * MAX_FREQ / WF_BINS / 2**MAX_ZOOM
    return counter, start_frequency_

def kiwi_start_freq(freq, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    return start_freq

def kiwi_end_freq(freq, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    end_freq = freq + span_khz/2
    return end_freq

def kiwi_offset_to_bin(freq, offset_khz, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    bins_per_khz = WF_BINS / span_khz
    return bins_per_khz * (offset_khz + span_khz/2)

def kiwi_bins_to_khz(freq, bins, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    bins_per_khz = WF_BINS / span_khz
    return (1./bins_per_khz) * (bins) + start_freq

def kiwi_receive_spectrum(wf_data, white_flag=False):
    msg = wf_stream.receive_message()
    if bytearray2str(msg[0:3]) == "W/F": # this is one waterfall line
        msg = msg[16:] # remove some header from each msg
        
        spectrum = np.ndarray(len(msg), dtype='B', buffer=msg).astype(np.float32) # convert from binary data to uint8
        wf = spectrum
        wf = -(255 - wf)  # dBm
        wf_db = wf - 13 # typical Kiwi wf cal
        dyn_range = (np.max(wf_db[1:-1])-np.min(wf_db[1:-1]))
        wf_color =  (wf_db - np.min(wf_db[1:-1]))
        # standardize the distribution between 0 and 1
        wf_color /= np.max(wf_color[1:-1])
        # clip extreme values
        wf_color = np.clip(wf_color, np.percentile(wf_color,CLIP_LOWP), np.percentile(wf_color, CLIP_HIGHP))
        # standardize again between 0 and 255
        wf_color -= np.min(wf_color[1:-1])
        # expand between 0 and 255
        wf_color /= (np.max(wf_color[1:-1])/255.)
        # avoid too bright colors with no signals
        wf_color *= (min(dyn_range, MIN_DYN_RANGE)/MIN_DYN_RANGE)
        # insert a full signal line to see freq/zoom changes
        if white_flag:
            wf_color = np.ones_like(wf_color)*255
        wf_data[-1,:] = wf_color
        wf_data[0:length-1,:] = wf_data[1:length,:]
    
    return wf_data 

def cat_get_freq(cat_socket):
    cat_socket.send("+f\n")
    out = cat_socket.recv(512)
    freq_ = int(out.split(" ")[1].split("\n")[0])/1000.
    return freq_

def cat_get_mode(cat_socket):
    cat_socket.send("m\n")
    out = cat_socket.recv(512)
    radio_mode_ = out.split("\n")[0]
    return radio_mode_

def kiwi_set_freq_zoom(freq_, zoom_, s_):
    start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    end_f_khz_ = kiwi_end_freq(freq_, zoom_)
    if zoom_ == 0:
        print("zoom 0 detected!")
        freq_ = 15000
        start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    else:
        if start_f_khz_<0:
            freq_ -= start_f_khz_
            start_f_khz_ = kiwi_start_freq(freq_, zoom_)

        if end_f_khz_>MAX_FREQ:
            freq_ -= end_f_khz_ - MAX_FREQ
            start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz_)
    if zoom_>0 and actual_freq<=0:
        freq_ = kiwi_zoom_to_span(zoom_)
        start_f_khz_ = kiwi_start_freq(freq_, zoom_)
        cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz_)
    msg = "SET zoom=%d start=%d" % (zoom_,cnt)
    wf_stream.send_message(msg)
    if s_ and freq_ >= 100:
        s_.send("F %d\n" % (freq_*1000))
        out = s_.recv(512)
    return freq_

def update_textsurfaces(freq, zoom, radio_mode):
    #           Label   Color   Freq/Mode                       Screen position
    ts_dict = {"freq": (GREEN, "%.2fkHz %s"%(freq, radio_mode), (wf_width/2-60,0)),
            "left": (GREEN, "%.1f"%(kiwi_start_freq(freq, zoom)) ,(0,0)),
            "right": (GREEN, "%.1f"%(kiwi_end_freq(freq, zoom)), (wf_width-80,0))}

    draw_dict = {}
    for k in ts_dict:
        draw_dict[k] = smallfont.render(ts_dict[k][1], False, ts_dict[k][0])
    return draw_dict, ts_dict

def draw_textsurfaces(draw_dict, ts_dict, sdrdisplay):
    for k in draw_dict:
        size = len(ts_dict[k][1])
        x_r, y_r = ts_dict[k][2]
        pygame.draw.rect(sdrdisplay, D_GREY, (x_r, y_r, size*11, 19), 0)
        #pygame.draw.rect(sdrdisplay, GREY, (x_r, y_r, size*11, 19), 1)
        sdrdisplay.blit(draw_dict[k], (x_r, y_r))

def draw_lines(surface, center_freq_bin, freq, wf_height, radio_mode, zoom, mouse):
    pygame.draw.line(surface, (250,250,250), (center_freq_bin, 0), (center_freq_bin, wf_height), 1)
    if "USB" in radio_mode:
        freq_bin = kiwi_offset_to_bin(freq, 3, zoom)
        pygame.draw.line(surface, (200,200,200), (freq_bin, 0), (freq_bin, wf_height), 1)
    elif "LSB" in radio_mode:
        freq_bin = kiwi_offset_to_bin(freq, -3, zoom)
        pygame.draw.line(surface, (200,200,200), (freq_bin, 0), (freq_bin, wf_height), 1)
    elif "CW" in radio_mode:
        freq_bin = kiwi_offset_to_bin(freq, -0.35, zoom)
        pygame.draw.line(surface, (200,200,200), (freq_bin, 0), (freq_bin, wf_height), 1)
        freq_bin = kiwi_offset_to_bin(freq, 0.35, zoom)
        pygame.draw.line(surface, (200,200,200), (freq_bin, 0), (freq_bin, wf_height), 1)

    pygame.draw.line(surface, (250,100,50), (mouse[0], 0), (mouse[0], wf_height), 1)


parser = OptionParser()
parser.add_option("-s", "--kiwiserver", type=str,
                  help="KiwiSDR server name", dest="kiwiserver", default='192.168.1.82')
parser.add_option("-p", "--kiwiport", type=int,
                  help="port number", dest="kiwiport", default=8073)
parser.add_option("-S", "--radioserver", type=str,
                  help="RTX server name", dest="radioserver", default=None)
parser.add_option("-P", "--radioport", type=int,
                  help="port number", dest="radioport", default=4532)
parser.add_option("-z", "--zoom", type=int,
                  help="zoom factor", dest="zoom", default=10)
parser.add_option("-f", "--freq", type=int,
                  help="center frequency in kHz", dest="freq", default=14060)
                  
options = vars(parser.parse_args()[0])

# Hardcoded values for most kiwis
MAX_FREQ = 30000. # 32000 # this should be dynamically set after connection
MAX_ZOOM = 14.
WF_BINS  = 1024.
DISPLAY_WIDTH = int(WF_BINS)
DISPLAY_HEIGHT = 400

MIN_DYN_RANGE = 70. # minimum visual dynamic range in dB
CLIP_LOWP, CLIP_HIGHP = 40., 100 # clipping percentile levels

# kiwi hostname and port
kiwihost = options['kiwiserver']
kiwiport = options['kiwiport']
print ("KiwiSDR Server: %s:%d" % (kiwihost, kiwiport))

#rigctld hostname and port
radiohost = options['radioserver']
radioport = options['radioport']
print ("RTX rigctld server: %s:%d" % (radiohost, radioport))
cat_flag = True
if not radiohost:
    cat_flag = False

# kiwi RX parameters
zoom = options['zoom']
print ("Zoom factor:", zoom)
freq = options['freq'] # this is the central freq in kHz
start_f_khz = kiwi_start_freq(freq, zoom)
cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz)
print ("Actual frequency:", actual_freq, "kHz")


########################## W/F connection
# connect to kiwi server
print ("Trying to contact server...")
try:
    kiwisocket = socket.socket()
    kiwisocket.connect((kiwihost, kiwiport))
except:
    print ("Failed to connect")
    exit()   
print ("Socket open...")

uri = '/%d/%s' % (int(time.time()), 'W/F')
handshake_wf = wsclient.ClientHandshakeProcessor(kiwisocket, kiwihost, kiwiport)
handshake_wf.handshake(uri)
request_wf = wsclient.ClientRequest(kiwisocket)
request_wf.ws_version = mod_pywebsocket.common.VERSION_HYBI13
stream_option_wf = StreamOptions()
stream_option_wf.mask_send = True
stream_option_wf.unmask_receive = False

wf_stream = Stream(request_wf, stream_option_wf)
print ("Waterfall data stream active...")

# send a sequence of messages to the server, hardcoded for now
# max wf speed, no compression
msg_list = ['SET auth t=kiwi p=', 'SET zoom=%d start=%d'%(zoom,cnt),\
'SET maxdb=0 mindb=-100', 'SET wf_speed=4', 'SET wf_comp=0', 'SET maxdb=-10 mindb=-110']
for msg in msg_list:
    wf_stream.send_message(msg)
print ("Starting to retrieve waterfall data...")


########################### SND connection
# connect to kiwi server
print ("Trying to contact server...")
try:
    kiwisocket_snd = socket.socket()
    kiwisocket_snd.connect((kiwihost, kiwiport))
except:
    print ("Failed to connect")
    exit()   
print ("Socket open...")

uri = '/%d/%s' % (int(time.time()), 'SND')
handshake_snd = wsclient.ClientHandshakeProcessor(kiwisocket_snd, kiwihost, kiwiport)
handshake_snd.handshake(uri)
request_snd = wsclient.ClientRequest(kiwisocket_snd)
request_snd.ws_version = mod_pywebsocket.common.VERSION_HYBI13
stream_option_snd = StreamOptions()
stream_option_snd.mask_send = True
stream_option_snd.unmask_receive = False

snd_stream = Stream(request_snd, stream_option_snd)
print ("Audio data stream active...")

on=True
hang=False
thresh=-70
slope=6
decay=1000
gain=50
mod="usb"
lc=30
hc=3000
freq=7074

msg_list = ["SET auth t=kiwi p=sibamanna", "SET mod=%s low_cut=%d high_cut=%d freq=%.3f" % (mod, lc, hc, freq),
"SET compression=0", "SET ident_user=pippo","SET OVERRIDE inactivity_timeout=1000",
"SET agc=%d hang=%d thresh=%d slope=%d decay=%d manGain=%d" % (on, hang, thresh, slope, decay, gain),
"SET AR OK in=%d out=%d" % (12000, 48000)]
print (msg_list)
for msg in msg_list:
    snd_stream.send_message(msg)


length = DISPLAY_HEIGHT

# create a numpy array to contain the waterfall data
wf_data = np.zeros((length, int(WF_BINS)))

# create a socket to communicate with rigctld
if cat_flag:
    cat_socket = socket.socket()
    cat_socket.connect((radiohost, radioport))
    radio_mode = cat_get_mode()
else:
    s = None
    radio_mode = "USB"

# init pygame basic objects
pygame.init()
sdrdisplay = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
wf_width = sdrdisplay.get_width()
wf_height = sdrdisplay.get_height()
smallfont = pygame.font.SysFont('Mono',18)
i_icon = "icon.jpg"
icon = pygame.image.load(i_icon)
pygame.display.set_icon(icon)
pygame.display.set_caption("KIWISDR WATERFALL")
clock = pygame.time.Clock()
pygame.key.set_repeat(100, 200)

# setup colormap from matplotlib
palRGB = cm.jet(range(256))[:,:3]*255

wf_quit = False

new_freq = freq
input_freq_flag = False
show_help_flag =  False
question = "Freq (kHz)"
current_string = []

import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000

play = pyaudio.PyAudio()
audio_buffer = []
for i in range(200):
    audio_buffer.append(np.zeros((512)))

# define callback (2)
def callback(in_data, frame_count, time_info, status):
    global audio_buffer
    factor = 48000/12000.
    popped = audio_buffer.pop(0)
    for _ in range(19):
        popped_ = audio_buffer.pop(0)
        popped = np.concatenate((popped, popped_), axis=0)
    n  = len(popped)
    xa = np.arange(round(n*factor))/factor
    xp = np.arange(n)
    pyaudio_buffer = np.round(np.interp(xa,xp,popped)).astype(np.int16)
    #print("LEN",len(pyaudio_buffer), 512*10*4)
    return (pyaudio_buffer, pyaudio.paContinue)

# open stream using callback (3)
stream = play.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                output_device_index=4,
                frames_per_buffer=512*20*4,
                stream_callback=callback)

stream.start_stream()

# fill buffer with silence at the beginning


while not wf_quit:
    #print(stream.is_active())
    print(len(audio_buffer))
    #print([np.sum(el) for el in audio_buffer])

    mouse = pygame.mouse.get_pos()
    click_freq = None
    change_zoom_flag = False
    change_freq_flag = False
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            show_help_flag = False
            if not input_freq_flag:
                keys = pygame.key.get_pressed()
                shift_mult = 10. if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1.

                if keys[pygame.K_DOWN]:
                    if zoom>0:
                        zoom -= 1
                        click_freq = freq
                        change_zoom_flag = True
                elif keys[pygame.K_UP]:
                    if zoom<MAX_ZOOM:
                        zoom += 1
                        click_freq = freq
                        change_zoom_flag = True
                elif keys[pygame.K_LEFT]:
                    if radio_mode!="CW":
                        click_freq = round(freq - 1*shift_mult)
                    else:
                        click_freq = (freq - 0.1*shift_mult)
                elif keys[pygame.K_RIGHT]:
                    if radio_mode!="CW":
                        click_freq = round(freq + 1*shift_mult)
                    else:
                        click_freq = (freq + 0.1*shift_mult)
                elif keys[pygame.K_PAGEDOWN]:
                    click_freq = freq - 1000
                elif keys[pygame.K_PAGEUP]:
                    click_freq = freq + 1000
                elif keys[pygame.K_u]:
                    if s:
                        cat_socket.send("+M USB 2400\n")
                        out = cat_socket.recv(512)
                    else:
                        radio_mode = "USB"
                elif keys[pygame.K_l]:
                    if s:
                        cat_socket.send("+M LSB 2400\n")
                        out = cat_socket.recv(512)
                    else:
                        radio_mode = "LSB"
                elif keys[pygame.K_c]:
                    if s:
                        cat_socket.send("+M CW 500\n")
                        out = cat_socket.recv(512)
                    else:
                        radio_mode = "CW"
                elif keys[pygame.K_f]:
                    input_freq_flag = True
                    current_string = []
                    #click_freq = int(inputbox.ask(sdrdisplay, 'Freq (kHz)'))
                elif keys[pygame.K_h]:
                    show_help_flag = True
                elif keys[pygame.K_ESCAPE] and keys[pygame.K_LSHIFT]:
                    wf_quit = True
            else:
                inkey = event.key
                if inkey in allowed_sym:
                    if inkey == pygame.K_BACKSPACE:
                        current_string = current_string[0:-1]
                    elif inkey == pygame.K_RETURN:
                        current_string = "".join(current_string)
                        try:
                            click_freq = int(current_string)
                        except:
                            pass
                        input_freq_flag = False
                    elif inkey == pygame.K_ESCAPE:
                        input_freq_flag = False
                        print("ESCAPE!")
                    else:
                        current_string.append(chr(inkey))
                display_box(sdrdisplay, question + ": " + "".join(current_string))

        if event.type == pygame.QUIT:
            wf_quit = True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            click_freq = kiwi_bins_to_khz(freq, mouse[0], zoom)

    if click_freq or change_zoom_flag:
        freq = kiwi_set_freq_zoom(click_freq, zoom, s)
        print(freq) 
    if cat_flag:
        new_freq = cat_get_freq()
        radio_mode = cat_get_mode()
        if freq != new_freq:
            freq = new_freq
            freq = kiwi_set_freq_zoom(freq, zoom, s)
     
    draw_dict, ts_dict = update_textsurfaces(freq, zoom, radio_mode)

    if random.random()>0.95:
        wf_stream.send_message('SET keepalive')
        snd_stream.send_message('SET keepalive')
    
    snd_buf = process_audio_stream()
    if snd_buf is not None:
        audio_buffer.append(snd_buf)
        #print(snd_buf)
    else:
        print("!")

#   plot horiz line to show time of freq change
    wf_data = kiwi_receive_spectrum(wf_data, True if click_freq or change_zoom_flag else False)

    surface = pygame.surfarray.make_surface(wf_data.T)

    surface.set_palette(palRGB)
    center_freq_bin = kiwi_offset_to_bin(freq, 0, zoom)
    
    draw_lines(surface, center_freq_bin, freq, wf_height, radio_mode, zoom, mouse)
    
    sdrdisplay.blit(surface, (0, 0))
    draw_textsurfaces(draw_dict, ts_dict, sdrdisplay)
    if input_freq_flag:
        display_box(sdrdisplay, question + ": " + "".join(current_string))
    elif show_help_flag:
        display_help_box(sdrdisplay, HELP_MESSAGE_LIST)

    pygame.display.update()
    clock.tick(1000)
    mouse = pygame.mouse.get_pos()

pygame.quit()
try:
    wf_stream.close_connection(mod_pywebsocket.common.STATUS_GOING_AWAY)
    kiwisocket.close()
except Exception as e:
    print ("exception: %s" % e)