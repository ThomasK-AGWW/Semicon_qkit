# ZI_HDAWG4 driver
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#import subprocess
#subprocess.Popen(['ziDataServer'], shell = True) 
#import os
#os.spawnl(os.P_DETACH, 'ziDataServer')

import logging
import matplotlib.pyplot as plt
import numpy as np
import os
from pathlib import Path
import qkit
from qkit.core.instrument_base import Instrument
import shutil
import sys
import textwrap
import time
from time import sleep
import zhinst 
import zhinst.utils
from zhinst.toolkit import Session, Waveforms
import json


class ZI_HDAWG4(Instrument):

    #input to initialize instrument: name(string) - name of the instrument, device_id - serial numer of instrument
    def __init__(self, name, device_id, disable_everything = False, **kwargs):
        """ 
        DOCUMENTATION

        __init__: ZI_HDAWG4 (parent class: Instrument)

            initialization parameters:

            name (STRING):
                name of the device
            device_id (string):
                number of the device

            work parameters (see methods descriptions for further information):

            marker_output (INT)
            output_range (FLOAT)
            sampling_rate (INT)
            channel_grouping (INT)
            user_regs (INT)
            direct (INT)
            delay (FLOAT
            channel_output (INT)
            #wave_output (INT)
            amplitude (FLOAT
            modulation_mode (INT)



        """
        logging.info(__name__ + ' : Initializing instrument')
        Instrument.__init__(self, name, tags = ['physical','ZI_HDAWG4'])


        self._device_id = device_id

        #auxiliary variables
        #array to translate channel number into binary
        self._binary = np.array([[0,0],[0,1],[1,0],[1,1]])
        #maximum length of waveform (in samples, in order to set trigger)
        self._waveform_max_length = 0

        #arrays containing information about which channel of the device are switched on
        #and which wave and marker outputs are used
        #all of them are off per default
        #self._wave_outputs = np.array([0,0,0,0])
        self._marker_outputs = np.array([0,0,0,0])
        self._channel_outputs = np.array([0,0,0,0])
        
        #Sample clock prescaler values:
        self._prescaler = np.array([2**i for i in range(14)])
        
        #Possible voltage ranges for outputs
        self._Vrange_array = np.array([0.2, 0.4, 0.6, 0.8, 1., 2., 3., 4., 5.])

        #Limiter for output range
        self._max_Vrange = 5 # in V

        #Turn text output of waveform upload on and off
        self._console_output = True

        #set apilevel to highest supported by device to unlock most of the functionalities
        #create apisession to communicate with device (ziDataServer needed)
        self._apilevel = 6
        self._bad_device_message = "No ZI_HDAWG4 device found."
        (self.daq, self.device, _) = zhinst.utils.create_api_session(self._device_id, self._apilevel) 
        zhinst.utils.api_server_version_check(self.daq)

        ### connect to data server
        session = Session('localhost')
        ### connect to device
        self.device_new = session.connect_device(self._device_id)

        #create instance of awgModule
        self.awgModule = self.daq.awgModule()
        self.awgModule.set("device", self.device)
        self.awgModule.execute()

        #path of the module folder
        self.data_dir = self.awgModule.getString("directory")
        logging.info(__name__+'Module folder set: '+self.data_dir)

        #path of the folder in which waveforms are saved (only this specific folder is possible)
        self.wave_dir = str(os.path.join(self.data_dir, "awg", "waves"))+'/'
        logging.info(__name__+'Waveform folder set: '+self.wave_dir)

        # disable all outputs etc.
        if disable_everything:
            self.disable_everything()

        #implement functions
        self.add_function("start_playback")
        self.add_function("stop_playback")
        self.add_function('refresh_folder')
        self.add_function('write')
        self.add_function('set_program_string')
        self.add_function('upload_to_device')
        self.add_function('load_config_file')
        self.add_function('disable_everything')

        #/TRIGGERS/OUT/n/SOURCE
        self.add_parameter('marker_output', type = int,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = "ch%d_",
            minval = 0, maxval = 2,
            tags = ['sweep'])

        #/SIGOUTS/n/RANGE
        self.add_parameter('output_range', type = float,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = "ch%d_",
            minval = 0.2, maxval = 5,
            units = 'V', tags = ['fixed values'])

       #/SIGOUTS
        self.add_parameter('voltage_offset', type = float,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = "ch%d_",
            minval = -5, maxval = 5,
            tags = ['sweep'])

        #/SYSTEM/CLOCKS/SAMPLECLOCK/FREQ
        self.add_parameter('sampling_clock', type = float,
            flags = Instrument.FLAG_GETSET,
            minval = 100e6, maxval = 2.4e9,
            tags = ['sweep'])
        
        #/AWGS/n/TIME
        self.add_parameter('sampling_prescaler', type = int,
            flags = Instrument.FLAG_GETSET,
            minval = 0, maxval = 8192,
            tags = ['sweep'])
        
        #Actual sampling rate
        self.add_parameter('sampling_rate', type = float,
            flags = Instrument.FLAG_GET)
        
        #/SYSTEM/AWG/CHANNELGROUPING
        self.add_parameter('channel_grouping', type = int,
            flags = Instrument.FLAG_GETSET,
            minval = 0, maxval = 1,
            tags = ['sweep'])

        #/AWGS/n/USERREGS/n
        # there are 32 user registers that the sequencer has access to
        # usage: communicate information to API program
        self.add_parameter('user_regs', type = int,
            flags = Instrument.FLAG_GETSET,
            channels = (1,32), channel_prefix = 'reg%d_',
            tags = ['sweep'])

        #/SIGOUTS/0/DIRECT
        self.add_parameter('direct', type = int,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = 'ch%d_',
            minval = 0, maxval = 1,
            tags = ['sweep'])

        #/SIGOUTS/0/DELAY
        self.add_parameter('delay', type = float,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = 'ch%d_',
            minval = 0,maxval = 25.83e-9,
            units = 's', tags = ['sweep'])

        #/SIGOUTS/n/ON
        self.add_parameter('channel_output', type = int,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = "ch%d_",
            minval = 0, maxval = 1,
            tags = ['sweep'])

        ## wave outputs, using channel_output
        #self.add_parameter('wave_output', type = int,
        #    flags = Instrument.FLAG_GETSET,
        #    channels = (1,4), channel_prefix = "ch%d_",
        #    minval = 0, maxval = 1,
        #    tags = ['sweep'])

        #/AWGS/n/OUTPUTS/n/AMPLITUDE
        self.add_parameter('amplitude', type = float,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = "ch%d_",
            tags = ['sweep'])

        #/AWGS/n/OUTPUTS/n/MODULATION/MODE 
        self.add_parameter('modulation_mode', type = int,
            flags = Instrument.FLAG_GETSET,
            channels = (1,4), channel_prefix = 'ch%d_',
            minval = 0, maxval = 5,
            tags = ['sweep'])
        
        #Actual voltage limit
        self.add_parameter('voltage_limit', type = float,
            flags = Instrument.FLAG_GETSET,
            minval = 0, maxval = 5,
            tags = ['sweep'])
        
        # Add console_output
        self.add_parameter('console_output', type = bool,
            flags = Instrument.FLAG_GETSET,
            minval = 0, maxval = 1,
            tags = ['sweep'])
        

    def _do_set_modulation_mode(self,new,channel):

        if new == 0:
            logging.info(__name__+ ': Switching channel %d modulation off.'% channel)
        if new == 1:
            logging.info(__name__+ ': Switching channel %d modulation to sine 11 / 33.'% channel)
        if new == 2:
            logging.info(__name__+ ': Switching channel %d modulation to sine 22 / 44.'% channel)
        if new == 3:
            logging.info(__name__+ ': Switching channel %d modulation to sine 12 / 34.'% channel)
        if new == 4:
            logging.info(__name__+ ': Switching channel %d modulation to sine 21 / 43.'% channel)
        if new == 5:
            logging.info(__name__+ ': Switching channel %d modulation to advanced.'% channel)

        self.daq.setInt('/%s/AWGS/%d/OUTPUTS/%d/MODULATION/MODE'% (self.device, self._binary[channel-1][0], self._binary[channel-1][1]), new)
        self.daq.sync()

    def _do_get_modulation_mode(self, channel):

        output = self.daq.getInt('/%s/AWGS/%d/OUTPUTS/%d/MODULATION/MODE'% (self.device, self._binary[channel-1][0], self._binary[channel-1][1]))

        if output == 0:
            logging.info(__name__+ ': Channel %d modulation: off.'% channel)
        if output == 1: 
            logging.info(__name__+ ': Channel %d modulation: sine 11 / 33.'% channel)
        if output == 2:
            logging.info(__name__+ ': Channel %d modulation: sine 22 / 44.'% channel)
        if output == 3:
            logging.info(__name__+ ': Channel %d modulation: sine 12 / 34.'% channel)
        if output == 4:
            logging.info(__name__+ ': Channel %d modulation: sine 21 / 43.'% channel)
        if output == 5:
            logging.info(__name__+ ': Channel %d modulation: advanced.'% channel)

        return output

    #Amplitude (units of full scale) AWG Output (has to be <= 1 !!)
    def _do_set_amplitude(self, new, channel):

        logging.info(__name__ + ': Setting amplitude channel %d to %s (units of full scale)'% (channel, str(new)))

        self.daq.setDouble('/%s/awgs/%d/outputs/%d/amplitude'% (self.device, self._binary[channel-1][0], self._binary[channel-1][1]), new)
        self.daq.sync()

    def _do_get_amplitude(self, channel):

        output = self.daq.getDouble('/%s/awgs/%d/outputs/%d/amplitude'% (self.device, self._binary[channel-1][0], self._binary[channel-1][1]))

        logging.info(__name__ + ': Reading amplitude channel %d: %s (units of full scale)'% (channel, str(output)))
        return output

    #def _do_set_wave_output(self, new, channel):

    #    #switch on channel if output is used as wave output 
    #    #use set_channel_output to switch channel off, new = 0 will only swith off wave output
    #    if new == 1:
    #        exec('self.set_ch%d_channel_output(1)'% channel)

    #    #set channel on device
    #    self.daq.sync()

    #    #logging information
    #    if new == 1:
    #        logging.info(__name__ + ': Switching channel %d wave output on'% channel)
    #    else:
    #        logging.info(__name__ + ': Switching channel %d wave output off'% channel)

    #    #save wave output information for further processing
    #    self._wave_outputs[channel-1] = new

    #def _do_get_wave_output(self, channel):

    #    #readout
    #    output = self.daq.getInt('/%s/sigouts/%d/on'% (self._device_id, channel-1))

    #    #logging information
    #    if output == 1:
    #        logging.info(__name__ + ': Channel %d wave output is on'% channel)
    #    else:
    #        logging.info(__name__ + ': Channel %d wave output is off'% channel)

    #    return output

    def _do_set_channel_output(self, new, channel):

        #set channel on device
        self.daq.setInt('/%s/sigouts/%d/on'% (self.device, channel-1), new)
        self.daq.sync()

        #logging information
        if new == 1:
            logging.info(__name__ + ': Switching channel %d output on'% channel)
        else:
            logging.info(__name__ + ': Switching channel %d output off'% channel)

        #save channel output information for further processing
        self._channel_outputs[channel-1] = new

    def _do_get_channel_output(self, channel):

        #readout
        output = self.daq.getInt('/%s/sigouts/%d/on'% (self._device_id, channel-1))

        #logging information
        if output == 1:
            logging.info(__name__ + ': Channel %d output is on'% channel)
        else:
            logging.info(__name__ + ': Channel %d output is off'% channel)

        return output

    def _do_set_marker_output(self, new, channel):
        """
        DOCUMENTATION

        set_chX_marker_output(new):

             Set marker output of channel 'X'

             parameters:

             new (INT): 0 (on), 1 (marker 1 on), 2 (marker 2 on)
             channel (INT): channel index 'X'·

        """
        #switch on channel if output is used as marker
        #use set_channel_output to switch channel off, new = 0 will only swith off marker
        if new == 1 or new == 2:
            exec('self.set_ch%d_channel_output(1)'% channel)

        #set marker on device
        settings_array = np.array([[0,4,5],[0,6,7]])
        self.daq.setInt('/%s/triggers/out/%d/source'% (self.device, channel-1), settings_array[(channel-1)%2][new])
        self.daq.sync()

        #logging information
        if new != 0:
            logging.info(__name__ + ': Marker %d set to channel %d'% (new, channel))
        else:
            logging.info(__name__ + ': Switching marker channel %d off'% (channel))

        #save marker information for further processing
        self._marker_outputs[channel-1] = new

    #read out marker setting on awg, return number of marker
    def _do_get_marker_output(self, channel):
        """
        DOCUMENTATION

        get_chX_marker_output():

             Get marker output of channel 'X'

             parameters:

             channel (INT): channel index 'X'·

             return value (INT): 0 (on), 1 (marker 1 on), 2 (marker 2 on)

        """
        #readout
        output = self.daq.getInt('/%s/triggers/out/%d/source'% (self._device_id, channel-1))

        #convert read out setting to number of array (read out for triggers will be ignored)
        try:
            settings_array = np.array([[0,4,5],[0,6,7]])
            result = np.where(settings_array[(channel-1)%2] == output)[0][0]
        except:
            result=0

        logging.info(__name__+ ': Reading marker %d on channel %d.'% (result, channel))
        return result

    def _do_set_delay(self,new,channel):
        """
        DOCUMENTATION

        set_chX_delay(new):

             Set delay of wave output channel 'X'

             parameters:

             new (FLOAT): 0 to 25.83e-9 s
             channel (INT): channel index 'X'·

        """
        logging.info(__name__+': setting delay to %s ' %new +'s.')
        self.daq.setDouble('/%s/SIGOUTS/%d/DELAY'%(self._device_id,channel-1), new)
        print('Delay set to '+str(self.daq.getDouble('/%s/SIGOUTS/%d/DELAY'%(self._device_id,channel-1)))+'s.')
        self.daq.sync()

    def _do_get_delay(self, channel):
        """
        DOCUMENTATION

        get_chX_delay(new):

             Get delay of wave output channel 'X'

             parameters:

             channel (INT): channel index 'X'·

             return value (FLOAT): 0 to 25.83e-9 s

        """
        logging.info(__name__+': getting delay.')
        return self.daq.getDouble('/%s/SIGOUTS/%d/DELAY'%(self._device_id,channel-1))

    def _do_set_direct(self,new,channel):
        """
        DOCUMENTATION

        set_chX_direct(new):

             Enable or disable direct mode of channel 'X'

             parameters:

             new (INT): 0 (disable), 1 (enable)
             channel (INT): channel index 'X'·

        """
        if new == 0:
            logging.info(__name__+ ': Switching channel %d direct mode off.'% channel)
        if new == 1:
            logging.info(__name__+ ': Switching channel %d direct mode on.'% channel)

        self.daq.setInt('/%s/SIGOUTS/%d/DIRECT'%(self._device_id,channel-1), new)
        self.daq.sync()

    def _do_get_direct(self, channel):
        """
        DOCUMENTATION

        get_chX_direct():

             Check if direct mode of channel 'X' is enabled

             parameters:

             channel (INT): channel index 'X'·

             return value (INT): 0 (disable), 1 (enable)

        """
        output=self.daq.getInt('/%s/SIGOUTS/%d/DIRECT'%(self._device_id,channel-1))
        if output == 0:
            logging.info(__name__+ ': Channel %d direct mode: off.'% channel)
        if output == 1: 
            logging.info(__name__+ ': Channel %d direct mode: on.'% channel)

        return output

    def _do_set_user_regs(self,new, channel):
        """
        DOCUMENTATION

        self.set_regX_user_regs(new)

             Set value of register 'X' 

             parameters:

             new (INT): arbitrary integer value
             channel (INT): channel index 'X'·

        """
        #translate channel number to nodes values
        _first_node_value = np.trunc((channel-1)/16)
        _second_node_value = (channel-1)%16


        self.daq.setInt('/%s/AWGS/%d/USERREGS/%d'% (self.device, _first_node_value, _second_node_value), new)
        self.daq.sync()
        logging.info(__name__ + ': User register %d value set to %d'% (channel, new))

    def _do_get_user_regs(self, channel):
        """
        DOCUMENTATION

        self.get_regX_user_regs()

             Get value of register 'X' 

             parameters:

             channel (INT): channel index 'X'·

             return value (INT): register value

        """
        #translate channel to nodes values
        _first_node_value = np.trunc((channel-1)/16)
        _second_node_value = (channel-1)%16

        output = self.daq.getInt('/%s/AWGS/%d/USERREGS/%d'% (self.device, _first_node_value, _second_node_value))
        logging.info(__name__ + ': User register register %d value is %d'% (channel, output))
        return output

    #set channel grouping, possible integer values for HDAWG4 are 0 (groups of 2) or 1 (groups of 4)
    def _do_set_channel_grouping(self,new):
        """
        DOCUMENTATION

        self.set_channel_grouping(new)

             Set value of register 'X' 

             parameters:

             new (INT): arbitrary integer value
             channel (INT): channel index 'X'·

        """
        if new == 0:
            logging.info(__name__+ ': Setting channel grouping to groups of 2.')
        if new == 1:
            logging.info(__name__+ ': Setting channel grouping to groups of 4.')
        self.daq.setInt('/%s/SYSTEM/AWG/CHANNELGROUPING' % self._device_id, new)
        self.daq.sync()

    def _do_get_channel_grouping(self):
        logging.info(__name__+': getting channel_grouping.')
        output = self.daq.getInt('/%s/SYSTEM/AWG/CHANNELGROUPING' % self._device_id)
        if output == 0:
            logging.info(__name__+ ': Channel grouping set to groups of 2.')
        if output == 1:
            logging.info(__name__+ ': Channel grouping set to groups of 4.')
        return output

    def _do_set_sampling_clock(self, newclock):
        logging.info(__name__+ ': Setting sample clock to %f.' % newclock)
        self.daq.setDouble('/%s/system/clocks/sampleclock/freq' % self._device_id, newclock)
        self.daq.sync()

    def _do_get_sampling_clock(self):
        logging.info(__name__+ ': Getting sample clock.')
        return self.daq.getDouble('/%s/system/clocks/sampleclock/freq' % self._device_id)
    
    def _do_set_sampling_prescaler(self, newdiv, core):
        if newdiv not in self._prescaler:
            raise ValueError(__name__ + " Could not set sampling prescaler, must be 2^n, with n between 0 and 13")            
        logging.info(__name__ +': Setting sampling prescaler to %d' % newdiv)
        exponent = np.floor(np.log2(np.abs(newdiv))).astype(int)
        if core == 0:
            self.daq.setInt('/%s/AWGS/0/TIME' % self._device_id, exponent)
        elif core == 1:
            self.daq.setInt('/%s/AWGS/1/TIME' % self._device_id, exponent)
        else: 
            raise ValueError("The core must be set to either 0 or 1. Value out of range.")

        self.daq.sync()

    def _do_get_sampling_prescaler(self):
        logging.info(__name__ +': getting sampling_prescaler')
        exponent = self.daq.getInt('/%s/AWGS/0/TIME' % self._device_id)        
        return 2**exponent
    
    def _do_get_sampling_rate(self):
        logging.info(__name__ +': getting sampling_rate')
        clock = self.daq.getDouble('/%s/system/clocks/sampleclock/freq' % self._device_id)
        prescaler = 2**self.daq.getInt('/%s/AWGS/0/TIME' % self._device_id)
        return clock/prescaler
        
    def _do_set_output_range(self,new,channel):
        if new not in self._Vrange_array:
            new = self._Vrange_array[np.searchsorted(self._Vrange_array,new,side = 'right')-1]
            logging.warning('Output voltage must be equal to one of the following values (in V): 0.2 / 0.4 / 0.8 / 1. / 1.5. / 2. / 3. / 4. / 5. \n Setting output to next lower value: '+str(new)+" V")
        logging.info(__name__+': setting output range of channel %s to %d' %(channel-1,new) +'V.')
        self.daq.setDouble('/%s/SIGOUTS/%d/RANGE' % (self._device_id, channel-1), new)
        self.daq.sync()

    def _do_get_output_range(self,channel):

        output = self.daq.getDouble('/%s/SIGOUTS/%d/RANGE' % (self._device_id, channel-1))
        logging.info(__name__+': output range of channel %s : %d' %(channel-1,output) +'V.')

        return output
    
    def _do_set_voltage_offset(self, new, channel, speed = 0.2, voltage_step = 1e-3):
        # readout channel offset
        init_voltage = self.daq.getDouble('/%s/sigouts/%d/offset'% (self._device_id, channel-1))
        voltage_array = np.arange(init_voltage, new, voltage_step)
        if speed == 0:
            raise ValueError("Speed cannot be set to 0")
        else:
            time_step = np.abs(new - init_voltage)/speed * voltage_step

         #set channel offset on device
        for volt in voltage_array:
            self.daq.setDouble('/%s/sigouts/%d/offset'% (self.device, channel-1), volt)
            time.sleep(time_step) 
        self.daq.sync()
       
        #logging information
        logging.info(__name__ + ': Switching channel %d offset on'% channel + 'to' + str(new) + 'V')

        #save channel output information for further processing
        self._channel_outputs[channel-1] = new

    def _do_get_voltage_offset(self, channel):
        #readout channel offset
        output = self.daq.getDouble('/%s/sigouts/%d/offset'% (self._device_id, channel-1))

        #logging information
        logging.info(__name__ + ': Channel %d output is on'% channel + 'to' + str(output) + 'V')
        return output
    
    def _do_set_voltage_limit(self, maxV):
        self._max_Vrange = maxV
        logging.info(__name__+': output range is limited to', maxV, 'V')

    def _do_get_voltage_limit(self):
        return self._max_Vrange
    
    def _do_set_console_output(self, output_bool):
        self._console_output = output_bool
        logging.info(__name__+': console output is set to', output_bool)

    def _do_get_console_output(self):
        return self._console_output

    #start awg sequencer
    def start_playback(self):
        self.daq.setInt(f"/{self.device}/awgs/0/enable", 1)

    #start awg sequencer
    def stop_playback(self):
        self.daq.setInt(f"/{self.device}/awgs/0/enable", 0)

    #disable everything
    def disable_everything(self):
        zhinst.utils.disable_everything(self.daq, self.device)
        logging.info(__name__+': all outputs etc. disabled')

    #create backup of folder "waves/" and empty it
    def refresh_folder(self):

        #if folder "waves/" already exists, create new folder and backup existing one
        if os.path.exists(self.wave_dir):
            #create backup folder name (folder in "awg/") using timestamp
            ts = int(time.time()) 
            folder = self.wave_dir.replace("waves/","")
            foldername = folder+'old_waves_backup_'+str(ts)

            #rename current waveform folder to backup folder
            shutil.move(self.wave_dir,foldername)
            logging.info(__name__+'Backup wavefolder created:'+str(foldername)+'.')

        #create new waveform folder
        os.mkdir(self.wave_dir)
        logging.info(__name__+'Wavefolder emptied.')

    #write sequence array to csv file and display preview
    #when used in a loop, stamp has to be equal to the iteration index
    #the input array for multiple channels must have the form (['channel1','channel2',...])
    #select preview plot by setting preview = 'yes' (default: 'no')
    def write(self,array,stamp = 1,preview = 'no'):

        #csv files are saved for channels 1 to 4 using A,B,C or D, respectively     
        channeldefinitions = (['A','B','C','D'])
        popiterator = 0#adjust to lenght of array channeldefinitions when element was removed
        for k in range(0, len(self._channel_outputs)):
            if self._channel_outputs[k] == 0:
                channeldefinitions.pop(k-popiterator)
                popiterator+=1
        #create new csv file 
        for u in range(0,len(array)):

            #check if waveform length is aligned to 16 (see AWG granularity in user manual)
            if len(array[u])%16!=0: 
                logging.warning(__name__+'Waveform number' +str(u)+': length has to be a multiple of 16.')
                input("Press Enter to continue, sequence array will probably be modified automatically.")

            filename = str(self.wave_dir)+"custom"+str(stamp)+channeldefinitions[u]+".csv"
            Path(filename).touch()

            #write array to csv file
            file = open(filename,'w')
            sequencearray = np.empty(0)

            for v in range(0,len(array[u])):
                file.write(str(array[u][v])+'\n')

            file.close()
            logging.info(__name__+'Waveform written to: '+str(filename))

            #preview
            if preview == 'yes':
                #preview with matplotlib and terminal output
                logging.info(__name__+'\nPartial sequence generated - array length (samples):'+str(len(array[u]))+'\n')

                x = range(0,len(array[u]))
                y = array[u]
                plt.plot(x,y)
                plt.title("sequence preview")
                plt.show()

            #give array length to self._waveform_max_length to set trigger in zcreate_sequence_program
            if (len(array[u])>self._waveform_max_length):
                self._waveform_max_length = len(array[u])



    #load own sequential C program from an arbitrary path (input as string)
    def set_program_string(self, program):
        if type(program) != str:
            raise TypeError(__name__ + ": Assigned value must be a string")
        self.awg_program = program
        logging.info(__name__+' : sequence program :\n\n'+self.awg_program+'\n\n')

    #compile and upload sequence to device
    def upload_to_device(self):

        #check if folder containing wave files exists
        if not os.path.isdir(self.wave_dir):
            raise Exception(f"Wave folder {self.wave_dir} does not exist or is not a directory.")

        #transfer and compile sequence program
        self.awgModule.set("compiler/sourcestring", self.awg_program)
        while self.awgModule.getInt("compiler/status") == -1:
            time.sleep(0.1)

        #raise exception if compilation has failed
        if self.awgModule.getInt("compiler/status") == 1:
            raise Exception(self.awgModule.getString("compiler/statusstring"))

        #upload messages
        if self.awgModule.getInt("compiler/status") == 0:
            print("Compilation successful (no warnings), uploading.")
        if self.awgModule.getInt("compiler/status") == 2:
            print("Compilation successful (with warnings), uploading.")
            print("Compiler warning: ", self.awgModule.getString("compiler/statusstring"))

        #wait until uploaded
        time.sleep(0.2)
        i = 0
        while (self.awgModule.getDouble("progress") < 1.0) and (self.awgModule.getInt("elf/status") != 1):
            print(f"{i} progress: {self.awgModule.getDouble('progress'):.2f}")
            time.sleep(0.2)
            i += 1
        print(f"{i} progress: {self.awgModule.getDouble('progress'):.2f}")
        if self.awgModule.getInt("elf/status") == 0:
            print("Upload successful.")
        if self.awgModule.getInt("elf/status") == 1:
            raise Exception("Upload failed.")

        #set single mode
        #According to Zurich Instruments:
        # "This is the preferred method of using the AWG: Run in single mode continuous waveform playback is best achieved by
        # using an infinite loop (e.g., while (true)) in the sequencer program."
        self.daq.setInt(f"/{self.device}/awgs/0/single", 1)

   # upload waveform from array
    def upload_waveform(self, awg_core, wave_dict):
        # Align wave_dict to 16 samples and adjust output voltage
        for channel in wave_dict.keys():
            # Set the output range for each channel
            if "Ch" in channel:
                    ## set output range automatically
                    maxV = np.max(np.abs(wave_dict[channel]))
                    if maxV > self._max_Vrange:
                        raise Exception("Output Range limit exceeded (max" +str(self._max_Vrange) + "V)")
                    else:
                        new = self._Vrange_array[np.searchsorted(self._Vrange_array, maxV, side = 'left')]
                    if awg_core == 0:
                        if self._console_output == True:
                            print("Setting ch" + str(channel[-1]) + " output range to " + str(new) + "V to match waveform data.")
                        self.set('ch' + str(channel[-1]) + '_output_range', new)
                    elif awg_core == 1:
                        if self._console_output == True:
                            print("Setting ch" + str(int(channel[-1]) + 2) + " output range to " + str(new) + "V to match waveform data.")
                        self.set('ch' + str(int(channel[-1]) + 2) + '_output_range', new)
                    wave_dict[channel] = wave_dict[channel]/new

            # Align the wave_dict to 16 samples
            if len(wave_dict[channel]) % 16 != 0:
                if self._console_output == True:
                    print(channel + " is not aligned to 16 samples and will be zero-extended")
                wave_dict[channel] = np.append(wave_dict[channel], np.zeros(16 - (len(wave_dict[channel])) % 16))
        if self._console_output == True:
            print("")

        # Define Sequencer Code and Waveform
        waveforms = Waveforms()
        sequencer = ''''''
        wave_names = ''

        c1 = "Ch1" in wave_dict.keys()
        c2 = "Ch2" in wave_dict.keys()
        m1 = "Trig1" in wave_dict.keys()
        m2 = "Trig2" in wave_dict.keys()
        
        # Look into what combinations of Waves and Markers exists and write sequencer code accordingly
        if c1 and c2:
            if m1 and m2:
                # wm1 and wm2
                sequencer += '''wave wm1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', true, false);\n'''
                sequencer += '''wave wm2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', true, false);\n'''
                wave_names += '1, wm1, '
                wave_names += '2, wm2, '

                # Create combined marker
                marker = np.zeros_like(wave_dict["Trig1"])
                marker[(wave_dict["Trig1"] == 0) & (wave_dict["Trig2"] == 0)] = 0b0000
                marker[(wave_dict["Trig1"] >= 1) & (wave_dict["Trig2"] == 0)] = 0b0001
                marker[(wave_dict["Trig1"] == 0) & (wave_dict["Trig2"] >= 1)] = 0b0100
                marker[(wave_dict["Trig1"] >= 1) & (wave_dict["Trig2"] >= 1)] = 0b0101
                waveforms[0] = (wave_dict["Ch1"], wave_dict["Ch2"], marker)
            elif m1:
                # wm1 and w2
                sequencer += '''wave wm1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', true, false);\n'''
                sequencer += '''wave w2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', false, false);\n'''
                wave_names += '1, wm1, '
                wave_names += '2, w2, '       

                # Create marker
                marker = np.zeros_like(wave_dict["Trig1"])
                marker[(wave_dict["Trig1"] >= 1)] = 0b0001
                marker[(wave_dict["Trig1"] == 0)] = 0b0000
                waveforms[0] = (wave_dict["Ch1"], wave_dict["Ch2"], marker)
            elif m2:
                # w1 and wm2
                sequencer += '''wave w1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', false, false);\n'''
                sequencer += '''wave wm2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', true, false);\n'''
                wave_names += '1, w1, '
                wave_names += '2, wm2, '

                # Create marker
                marker = np.zeros_like(wave_dict["Trig2"])
                marker[(wave_dict["Trig2"] == 0)] = 0b0000
                marker[(wave_dict["Trig2"] >= 1)] = 0b0100
                waveforms[0] = (wave_dict["Ch1"], wave_dict["Ch2"], marker)
            else:
                # w1 and w2
                sequencer += '''wave w1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', false, false);\n'''
                sequencer += '''wave w2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', false, false);\n'''
                wave_names += '1, w1, '
                wave_names += '2, w2, '
                waveforms[0] = (wave_dict["Ch1"], wave_dict["Ch2"])
        elif c1:
            if m1 and not m2:
                # wm1
                sequencer += '''wave wm1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', true, false);\n'''
                wave_names += '1, wm1, '

                # Create marker
                marker = np.zeros_like(wave_dict["Trig1"])
                marker[(wave_dict["Trig1"] >= 1)] = 1
                marker[(wave_dict["Trig1"] == 0)] = 2
                waveforms[0] = (wave_dict["Ch1"], marker)
            elif m2:
                raise Exception("Trig2 cannot be uploaded without providing a waveform")
            else:
                # w1
                sequencer += '''wave w1 = placeholder('''+ str(len(wave_dict["Ch1"])) + ''', false, false);\n'''
                wave_names += '1, w1, '
                waveforms[0] = (wave_dict["Ch1"])
        elif c2:
            if m2 and not m1:
                # wm2
                if self._console_output == True:
                    print("You just entered a dark cave. ")
                    print("This sequence is creating a dummy waveform to allow Marker2 to be played. \n")
                sequencer += '''wave dummy = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', false, false);\n'''
                sequencer += '''wave wm2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', true, false);\n'''
                wave_names += '1, dummy, '
                wave_names += '2, wm2, '

                # Create combined marker
                marker = np.zeros_like(wave_dict["Trig2"])
                marker[wave_dict["Trig2"] >= 1] = 3
                marker[wave_dict["Trig2"] == 0] = 4
                waveforms[0] = (np.zeros_like(wave_dict["Ch2"]), wave_dict["Ch2"], marker)
            elif m1:
                raise Exception("Trig1 cannot be uploaded without providing a waveform")
            else:
                sequencer += '''wave w2 = placeholder('''+ str(len(wave_dict["Ch2"])) + ''', false, false);\n'''
                wave_names += '2, w2, '
                waveforms[0] = (wave_dict["Ch2"])
        else:
            raise Exception("No waveform provided")

        sequencer += '''assignWaveIndex(''' + wave_names + str(0) + '''); \n'''
        sequencer += '''while(true){\nwaitDigTrigger(1);\nplayWave(''' + wave_names[:-2] + ''');\nwaitWave();\n}'''
        # sequencer += '''while(true){\nplayWave(''' + wave_names[:-2] + ''');\n}'''
        if self._console_output == True:
            print(sequencer, "\n")

        # Write sequencer code and upload waveform to the AWG
        awg_node = self.device_new.awgs[awg_core]
        awg_node.load_sequencer_program(sequencer)
        awg_node.wait_done()
        awg_node.write_to_waveform_memory(waveforms)
        
    #load config file from path
    def load_config_file(self, path):
        logging.info(__name__+': loading config file %s '% path)
        with open(path, 'r+') as f:
            config_data = json.load(f)
        #set sampling rate
        self.set_sampling_clock(config_data['device_settings'][0]['sampling_clock'])
        #set user registers
        for i in range(1,33):
            exec('self.set_reg%d_user_regs(%d)'%(i,int(config_data['device_settings'][0]['user_reg%d'% i])))
        #set channel grouping
        self.set_channel_grouping(config_data['device_settings'][0]['channel_grouping'])
        #set channel outputs on or off
        self.set_ch1_channel_output(config_data['device_settings'][0]['channel_output_channel1'])
        self.set_ch2_channel_output(config_data['device_settings'][0]['channel_output_channel2'])
        self.set_ch3_channel_output(config_data['device_settings'][0]['channel_output_channel3'])
        self.set_ch4_channel_output(config_data['device_settings'][0]['channel_output_channel4'])
        #set marker outputs (1 or 2) on or off
        self.set_ch1_marker_output(config_data['device_settings'][0]['marker_output_channel1'])
        self.set_ch2_marker_output(config_data['device_settings'][0]['marker_output_channel2'])
        self.set_ch3_marker_output(config_data['device_settings'][0]['marker_output_channel3'])
        self.set_ch4_marker_output(config_data['device_settings'][0]['marker_output_channel4'])
        #set channel output range
        self.set_ch1_output_range(config_data['device_settings'][0]['output_range_channel1'])
        self.set_ch2_output_range(config_data['device_settings'][0]['output_range_channel2'])
        self.set_ch3_output_range(config_data['device_settings'][0]['output_range_channel3'])
        self.set_ch4_output_range(config_data['device_settings'][0]['output_range_channel4'])
        #set channel amplitudes
        self.set_ch1_amplitude(config_data['device_settings'][0]['amplitude_channel1'])
        self.set_ch2_amplitude(config_data['device_settings'][0]['amplitude_channel2'])
        self.set_ch3_amplitude(config_data['device_settings'][0]['amplitude_channel3'])
        self.set_ch4_amplitude(config_data['device_settings'][0]['amplitude_channel4'])
        #set modulation mode
        self.set_ch1_modulation_mode(config_data['device_settings'][0]['modulation_mode_channel1'])
        self.set_ch2_modulation_mode(config_data['device_settings'][0]['modulation_mode_channel2'])
        self.set_ch3_modulation_mode(config_data['device_settings'][0]['modulation_mode_channel3'])
        self.set_ch4_modulation_mode(config_data['device_settings'][0]['modulation_mode_channel4'])
        #set direct mode
        self.set_ch1_direct(config_data['device_settings'][0]['direct_channel1'])
        self.set_ch2_direct(config_data['device_settings'][0]['direct_channel2'])
        self.set_ch3_direct(config_data['device_settings'][0]['direct_channel3'])
        self.set_ch4_direct(config_data['device_settings'][0]['direct_channel4'])

if __name__ == "__main__":
    qkit.start()

    #example for a sequence
    device_identification = 'dev8268'

    ###create ZI_HDAWG4 instance
    hartwig = qkit.instruments.create('hartwig','ZI_HDAWG4',device_id = device_identification)
    #load config file
    #hartwig.load_config_file('example_config_ZI_HDAWG4.json')

    #empty wave folder
    #hartwig.refresh_folder()

    #make new example sequence and save it to /awg/waves
    example_sequence_array = np.array([])
    for i in range(0,1600):
        for j in range(0,5):
            example_sequence_array = np.append(example_sequence_array,i)

    #write example_sequence_array to csv file
    #hartwig.zwrite([example_sequence_array])

    #load sequencer code that plays files in /awg/waves
    #hartwig.load_own_sequence_program('ZI_HDAWG4_testseq')

    #upload and play
   # hartwig.upload_to_device()

    #disable everything
    #hartwig.disable_everything()

    ##to add parameters, run the following program and copy and paste from file listofnodes
    #nodesmachine = qkit.instruments.create('hartwig','ZI_HDAWG4',device_id = device_identification)
    #nodes = nodesmachine.daq.listNodes('//',recursive = True,leavesonly = True)
    #x = 0
    #Path('listofnodes').touch()
    #with open('listofnodes','w') as f: 
    #    for elements in nodes:
    #        f.write('#'+str(elements)+'\n#self.add_parameter(\''+str(x)+'\', type = ,\n')
    #        f.write('    #flags = Instrument.FLAG_GETSET,\n')
    #        f.write('    #channels = (1,4), channel_prefix = \'ch%d_\',\n')
    #        f.write('    #minval = , maxval = ,\n    #units = \'\', tags = [\'sweep\'])\n\n')   
    #        f.write('')
    #        f.write('#def _do_set_'+str(x)+'(self,new,channel):\n')
    #        f.write('    #'+'logging.info(__name__+\': setting '+str(x)+' to %s \' %new +\'units.\')\n')
    #        f.write('    #self.daq.setDouble/setInt...(\''+str(elements)+'\'%self._device_id, new)\n')   
    #        f.write('    #self.daq.sync()\n\n')
    #        f.write('')
    #        f.write('#def _do_get_'+str(x)+'(self, channel):\n')
    #        f.write('    #'+'logging.info(__name__+\': getting '+str(x)+'.\')\n')
    #        f.write('    #return self.daq.getDouble/getInt(\''+str(elements)+'\'%self._device_id)\n\n') 
    #        x+=1
    #zhinst.utils.disable_everything(nodesmachine.daq,nodesmachine.device)
