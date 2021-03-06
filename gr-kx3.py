#!/usr/bin/env python

'''
This file is part of gr-kx3.

gr-kx3 is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

gr-kx3 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with gr-kx3.  If not, see <http://www.gnu.org/licenses/>.

Copyright 2012-2013 Darren Long darren.long@mac.com
'''

from datetime import datetime
from gnuradio import audio
from gnuradio import eng_notation
from gnuradio.fft import window
from gnuradio.eng_option import eng_option
from gnuradio import filter
from gnuradio.filter import firdes 
from gnuradio import blocks
from gnuradio.blocks import float_to_complex
from gnuradio.wxgui import fftsink2
from gnuradio.wxgui import forms
from gnuradio.wxgui import waterfallsink2
from grc_gnuradio import wxgui as grc_wxgui
from optparse import OptionParser
import math
import pexpect
import mutex
from threading import Thread, RLock
import time
import wx
from decimal import *
import traceback
import gc


##################################################
# some customisable values follow
##################################################
# fft and wf width in number of pixels (also sets number of bins). A power of 2 is optimal.
plot_width = 1100 #1280 #2300 # 2048 
# fft and wf height in number of pixels
plot_height = 600 
# make the whole thing smaller by this much (so you can see other things), try 0.75
gui_scale = 1.0
# rigctld poll rate in herz
rig_poll_rate = 5
# the sound device for I/Q data from the KX3, try "pulse" or something more fancy like "hw:CARD=PCH,DEV=0"
iq_device = "pulse"
# the sample rate for the I/Q input.  try 48000, 96000 or 192000
samp_rate = 48000
# fiddle with the dc_correction_length for best effect on the 0Hz artifact
dc_correction_length = 1024
# note that click-to-tune quantisation is set by the selected step size!

class grkx3(grc_wxgui.top_block_gui):

        def __init__(self):
                grc_wxgui.top_block_gui.__init__(self, title="gr-kx3")
                _icon_path = "/usr/share/icons/hicolor/32x32/apps/gnuradio-grc.png"
                self.SetIcon(wx.Icon(_icon_path, wx.BITMAP_TYPE_ANY))
                ##################################################
                # Variables
                ##################################################
                self.rig_freq = rig_freq = float(pexpect.run("rigctl -m 2 f"))
                self.rigctl = pexpect.spawn("rigctl -m 2")
                self.rigctl.timeout = 2.5
                self.prefix = prefix = "~/grdata"
                self.sync_freq = sync_freq = 3
                self.samp_rate = samp_rate
                self.recfile = recfile = prefix + datetime.now().strftime("%Y.%m.%d.%H.%M.%S") + ".dat"
                self.freq = freq = rig_freq
                self.click_freq = click_freq = 0
                self.step_up = step_up = 1
                self.dwell_up = dwell_up = 1
                self.step_down = step_down = 1
                self.dwell_down = dwell_down = 1
                self.step_size = step_size = 250
                self.ctq_step = self.step_size
                
                # calculate the number of FFT bins based on the width of the charts
                log_width = math.log(gui_scale * plot_width,2)
                if(0 != (log_width - int(log_width))):
                	log_width = log_width + 1
                num_bins = pow(2, int(log_width))
                print  "Setting number of FFT bins to:" + str(num_bins)
                
                ##################################################
                # Blocks
                ##################################################
                self.nb0 = self.nb0 = wx.Notebook(self.GetWin(), style=wx.NB_TOP)
                self.nb0.AddPage(grc_wxgui.Panel(self.nb0), "Waterfall")
                self.nb0.AddPage(grc_wxgui.Panel(self.nb0), "FFT")
                self.GridAdd(self.nb0, 2, 0, 5, 8)
                self.wxgui_waterfallsink2_0 = waterfallsink2.waterfall_sink_c(
                        self.nb0.GetPage(0).GetWin(),
                        baseband_freq=rig_freq,
                        dynamic_range=20,
                        ref_level=-80,
                        ref_scale=1.0,
                        sample_rate=samp_rate,
                        fft_size=num_bins,
                        fft_rate=30,
                        average=False,
                        avg_alpha=None,
                        title="Waterfall Plot",
                        win=window.hamming,
                        size=(plot_width*gui_scale,plot_height*gui_scale),
                )
                self.nb0.GetPage(0).Add(self.wxgui_waterfallsink2_0.win)
                def wxgui_waterfallsink2_0_callback(x, y):
                        self.set_click_freq(x)
                
                self.wxgui_waterfallsink2_0.set_callback(wxgui_waterfallsink2_0_callback)
                self.wxgui_fftsink2_0 = fftsink2.fft_sink_c(
                        self.nb0.GetPage(1).GetWin(),
                        baseband_freq=rig_freq,
                        y_per_div=10,
                        y_divs=12,
                        ref_level=0,
                        ref_scale=2.0,
                        sample_rate=samp_rate,
                        fft_size=num_bins,
                        fft_rate=10,
                        average=True,
                        avg_alpha=None,
                        title="FFT Plot",
                        peak_hold=True,
                        win=window.flattop,
                        size=(plot_width*gui_scale,plot_height*gui_scale),
                )
                self.nb0.GetPage(1).Add(self.wxgui_fftsink2_0.win)
                self.gr_float_to_complex_0 = blocks.float_to_complex(1)
                self._freq_text_box = forms.text_box(
                        parent=self.GetWin(),
                        value=self.freq,
                        callback=self.set_text_freq,
                        label="  Frequency (Hz)",
                        converter=forms.int_converter(),
                )
                self.GridAdd(self._freq_text_box, 1, 0, 1, 1)
                self._sync_freq_chooser = forms.drop_down(
                        parent=self.GetWin(),
                        value=self.sync_freq,
                        callback=self.set_sync_freq,
                        label="",
                        choices=[1,2,3],
                        labels=["Entry","Track","Track & Click"],
                )
                self.GridAdd(self._sync_freq_chooser, 1, 1, 1, 1)
                        
                self._dwell_down_chooser = forms.button(
                        parent=self.GetWin(),
                        value=self.dwell_down,
                        callback=self.set_dwell_down,
                        label="",
                        choices=[1],
                        labels=["FFT Down"],
                )
                self.GridAdd(self._dwell_down_chooser, 1, 2, 1, 1)		
                
                self._dwell_up_chooser = forms.button(
                        parent=self.GetWin(),
                        value=self.dwell_up,
                        callback=self.set_dwell_up,
                        label="",
                        choices=[1],
                        labels=["FFT Up"],
                )
                self.GridAdd(self._dwell_up_chooser, 1, 3, 1, 1)                
                
                self._step_size_chooser = forms.drop_down(
                        parent=self.GetWin(),
                        value=self.step_size,
                        callback=self.set_step_size,
                        label="\tStep",
                        choices=[1000000,100000,10000,1000,500,250,125,100,10],
                        labels=["1MHz","100kHz","10kHz","1kHz","500Hz","250Hz","125Hz","100Hz","10Hz"],
                )
                self.GridAdd(self._step_size_chooser, 1, 4, 1, 1)

                self._step_down_chooser = forms.button(
                        parent=self.GetWin(),
                        value=self.step_down,
                        callback=self.set_step_down,
                        label="",
                        choices=[1],
                        labels=["Step Down"],
                )
                self.GridAdd(self._step_down_chooser, 1, 5, 1, 1)		
                
                self._step_up_chooser = forms.button(
                        parent=self.GetWin(),
                        value=self.step_up,
                        callback=self.set_step_up,
                        label="",
                        choices=[1],
                        labels=["Step Up"],
                )
                self.GridAdd(self._step_up_chooser, 1, 6, 1, 1)

                self.audio_source_0 = audio.source(samp_rate, iq_device, True)
                self.dc_blocker_xx_0 = filter.dc_blocker_cc(dc_correction_length, True)
                
                ##################################################
                # Connections
                ##################################################
                self.connect((self.audio_source_0, 1), (self.gr_float_to_complex_0, 0))
                self.connect((self.audio_source_0, 0), (self.gr_float_to_complex_0, 1))
                self.connect((self.gr_float_to_complex_0, 0), (self.dc_blocker_xx_0, 0))
                self.connect((self.dc_blocker_xx_0, 0), (self.wxgui_waterfallsink2_0, 0))
                self.connect((self.dc_blocker_xx_0, 0), (self.wxgui_fftsink2_0, 0))  
                             
                self.lock = RLock()
                self.vfo_poll_skip = 0
                self.set_rig_vfo = False
                self.quit = False
                _poll_vfo_thread = Thread(target=self._poll_vfo_probe)
                _poll_vfo_thread.daemon = True
                _poll_vfo_thread.start()

        def quit(self):
            self.quit = True

        def skip_vfo_poll_CS(self):
            self.lock.acquire()
            if self.vfo_poll_skip >= 0:
                self.vfo_poll_skip = rig_poll_rate * 1
            self.lock.release()
            gc.collect()

        def should_skip_vfo_poll_CS(self):
            temp = self.vfo_poll_skip
            if temp != 0:
                if temp > 0:
                    self.vfo_poll_skip = temp - 1
                retval = True
            else:
                self.vfo_poll_skip = 0
                retval = False
            return retval

        def poll_vfo(self):
            retval = False
            self.poll_rigctl.sendline("f") 
            res = self.poll_rigctl.expect(["Frequency: ", pexpect.TIMEOUT])
            if res == 0:
                res = self.poll_rigctl.expect(["\r", pexpect.TIMEOUT])
                if res == 0:
                    rig_freq = self.poll_rigctl.before
                    self.set_rig_vfo = False
                    if int(rig_freq) != int(self.freq):
                        print "\n* poll_vfo(" + str(rig_freq) + ")"
                    self._freq_text_box.set_value(float(rig_freq))
                    retval = True
            return retval    

        def _poll_vfo_probe(self):
            self.poll_rigctl = pexpect.spawn("rigctl -m 2")
            self.poll_rigctl.timeout = 2.5
            reset_rigctl = False
            while True:
                    if True == self.quit:
                        print "Warning: _poll_vfo_probe() quiting!"
                        break
                    self.lock.acquire()
                    try:
                        if self.should_skip_vfo_poll_CS() == False:
                            # polling
                            if not self.poll_vfo():
                                reset_rigctl = True
                        else:
                            # skipping poll
                            pass
                    except AttributeError, e:
                        print "AttributeError in _poll_vfo_probe() ... rigctl error"
                        reset_rigctl = True
                    except ValueError, e:
                        print "ValueError in _poll_vfo_probe() ... rigctl error"
                        reset_rigctl = True
                    except Exception, e:
                        print "Exception in _poll_vfo_probe() ... unknown error"
                        reset_rigctl = True    
                    finally:
                        self.lock.release()
                    if True == reset_rigctl:
                        print "Warning: _poll_vfo_probe() resetting rigctl"
                        self.poll_rigctl.close()
                        self.poll_rigctl = pexpect.spawn("rigctl -m 2")
                        self.poll_rigctl.timeout = 2.5
                        reset_rigctl = False
                    time.sleep(1.0/(rig_poll_rate))
                    gc.collect()
                    
        def rig_respawn(self):
                self.rigctl.close()
                self.rigctl = pexpect.spawn("rigctl -m 2")
                self.rigctl.timeout = 2.5
        def get_rig_freq(self):
                return self.rig_freq

        def set_baseband_freq(self, rig_freq):
                self.rig_freq = rig_freq
                print"* set_baseband_freq(" + str(self.rig_freq) + ")"
                self.wxgui_waterfallsink2_0.set_baseband_freq(self.rig_freq)
                self.wxgui_fftsink2_0.set_baseband_freq(self.rig_freq)


        def get_prefix(self):
                return self.prefix

        def set_prefix(self, prefix):
                self.prefix = prefix
                self.set_recfile(self.prefix + datetime.now().strftime("%Y.%m.%d.%H.%M.%S") + ".dat")

        def get_step_size(self):
                return self.step_size

        def set_step_size(self, step_size):
                self.step_size = step_size
                self._step_size_chooser.set_value(self.step_size)
                self.ctq_step = self.step_size

        def get_step_up(self):
                return self.step_up

        def set_step_up(self, step_up):
                self.skip_vfo_poll_CS()
                self.set_rig_vfo = True
                self.step_up = step_up
                self._step_up_chooser.set_value(self.step_up)
                print "\n* set_step_up(" + str(self.freq + self.step_size) + ")"                
                self._freq_text_box.set_value(self.freq + self.step_size)
                 
        def get_step_down(self):
                return self.step_down

        def set_step_down(self, step_down):
                self.skip_vfo_poll_CS()
                self.set_rig_vfo = True
                self.step_down = step_down
                self._step_down_chooser.set_value(self.step_down)
                print "\n* set_step_down(" + str(self.freq - self.step_size) + ")"
                self._freq_text_box.set_value(self.freq - self.step_size)

        def get_dwell_up(self):
                return self.dwell_up

        def set_dwell_up(self, dwell_up):
                self.skip_vfo_poll_CS()
                self.set_rig_vfo = True
                self.dwell_up = dwell_up
                self._dwell_up_chooser.set_value(self.dwell_up)
                # step up one dwell, i.e. the sample rate
                print "\n* set_dwell_up(" + str(self.freq + (self.samp_rate)) + ")"
                self._freq_text_box.set_value(self.freq + (self.samp_rate))

        def get_dwell_down(self):
                return self.dwell_down

        def set_dwell_down(self, dwell_down):
                self.skip_vfo_poll_CS()
                self.set_rig_vfo = True
                self.dwell_down = dwell_down
                self._dwell_down_chooser.set_value(self.dwell_down)
                # step down one dwell, i.e. the sample rate
                print "\n* set_dwell_down(" + str(self.freq - (self.samp_rate)) + ")"
                self._freq_text_box.set_value(self.freq - (self.samp_rate))

        def get_samp_rate(self):
                return self.samp_rate

        def set_samp_rate(self, samp_rate):
                self.samp_rate = samp_rate
                self.wxgui_waterfallsink2_0.set_sample_rate(self.samp_rate)
                self.wxgui_fftsink2_0.set_sample_rate(self.samp_rate)

        def get_recfile(self):
                return self.recfile

        def set_recfile(self, recfile):
                self.recfile = recfile

        def get_freq(self):
                return self.freq

        def set_text_freq(self, freq):
            self.lock.acquire()
            if self.vfo_poll_skip > 0 and self.set_rig_vfo == False:
                print "* set_text_freq(" + str(self.freq) + ") ... ignoring"
            else:
                self.freq = freq
                print "* set_text_freq(" + str(int(self.freq)) + ")"
                if 1 == self.sync_freq or self.set_rig_vfo == True:
                    self.set_rig_vfo = False
                    self.set_rig_freq()
                self.set_baseband_freq(int(self.freq))
            self.lock.release()
        
        def set_rig_freq(self):
            print "* set_rig_freq(" + str(self.freq) + ")"
            self.rigctl.sendline("F " + str(self.freq))
            self.rigctl.expect("Rig command: ")

        def get_click_freq(self):
                return self.click_freq

        def set_click_freq(self, click_freq):
                if 3 == self.sync_freq:
                    self.skip_vfo_poll_CS()
                    self.click_freq = float(click_freq)
                    print "\n* set_click_freq(" + str(int(self.click_freq)) + ")"
                    self.set_rig_vfo = True
                    set_freq = Decimal(self.click_freq/float(self.ctq_step)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*Decimal(str(self.ctq_step))
                    self._freq_text_box.set_value(int(set_freq))
                               
        def get_sync_freq(self):
                return self.sync_freq

        def set_sync_freq(self, sync_freq):
                self.sync_freq = sync_freq
                self.lock.acquire()
                if 1 == self.sync_freq: # direct entry
                    self.vfo_poll_skip = -1
                elif 1 < self.sync_freq: # 2 is vfo tracking, 3 track and click
                    self.vfo_poll_skip = rig_poll_rate * 1
                self.lock.release()

if __name__ == '__main__':
        parser = OptionParser(option_class=eng_option, usage="%prog: [options]")
        (options, args) = parser.parse_args()
        tb = grkx3()
        try:
            tb.Run(True)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            exit_now = True;

