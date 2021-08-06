# -*- coding: utf-8 -*-
"""
Created on Sun Jul 30 17:53:14 2017

@author: Michael Oberhofer
"""

import socket
import logging
from time import sleep
import datetime as dt

log = logging.getLogger('oxygenscpi')

def isMinimumVersion(version, minVersion):
    if version[0] > minVersion[0]:
        return True
    elif version[0] < minVersion[0]:
        return False
    elif version[0] == minVersion[0]:
        if version[1] >= minVersion[1]:
            return True
        else:
            return False

class OxygenSCPI(object):
    def __init__(self, ipAddr, tcpPort = 10001):
        self._ipAddr = ipAddr
        self._tcpPort = tcpPort
        self._CONN_NUM_TRY = 3
        self._CONN_TIMEOUT = 2
        self._CONN_MSG_DELAY = 0.5
        self._TCP_BLOCK_SIZE = 4096
        self._sock = None
        #self.connect()
        self._headersActive = True
        self.channelList = []
        self._scpi_version = (1,5)
        self._value_dimension = None
        self.DataStream = OxygenScpiDataStream(self)

    def connect(self):
        for numTry in range(1, self._CONN_NUM_TRY+1):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 0)
            #sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, 0)
            sock.settimeout(self._CONN_TIMEOUT)
            try:
                sock.connect((self._ipAddr, self._tcpPort))
                self._sock = sock
                self.getVersion()
                return True
            except ConnectionRefusedError as msg:
                template = "Connection to {!s}:{:d} refused: {!s}"
                log.error(template.format(self._ipAddr, self._tcpPort, msg))
                sock = None
                return False
            except OSError as msg:
                if numTry < self._CONN_NUM_TRY:
                    continue
                template = "Connection to {!s}:{:d} failed: {!s}"
                sock = None
                log.error(template.format(self._ipAddr, self._tcpPort, msg))
                return False
        #if sock is not None:
        self._sock = sock
        #return False
        
    def disconnect(self):
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
        except OSError as msg:
                log.error("Error Shutting Down: %s" %  (msg))
        except AttributeError as msg:
                log.error("Error Shutting Down: %s" %  (msg))
        self._sock = None
        
    def _sendRaw(self, cmd):
        cmd += '\n'
        if self._sock is None:
            self.connect()
        if self._sock is not None:
            try:
                self._sock.sendall(cmd.encode())
                sleep(self._CONN_MSG_DELAY)
                return True
            except OSError as msg:
                self.disconnect()
                template = "{!s}"
                log.error(template.format(msg))
        return False
    
    def _askRaw(self, cmd):
        cmd += '\n'
        if self._sock is None:
            self.connect()
        if self._sock is not None:
            try:
                self._sock.sendall(cmd.encode())
                answerMsg = bytes(0)
                # TODO: Use EOL Character to detect End of Message
                while True:
                    data = self._sock.recv(self._TCP_BLOCK_SIZE)
                    if len(data) < self._TCP_BLOCK_SIZE:
                        answerMsg += data
                        return answerMsg
                    else:
                        answerMsg += data
            except OSError as msg:
                self.disconnect()
                template = "{!s}"
                log.error(template.format(msg))
        return False
            
    def getIdn(self):
        ret = self._askRaw('*IDN?')
        if type(ret) == bytes:
            return ret.decode().strip()
        else:
            return False
        
    def getVersion(self):
        """
        SCPI,"1999.0",RC_SCPI,"1.6",OXYGEN,"2.5.71"
        """
        ret = self._askRaw('*VER?')
        if type(ret) == bytes:
            ret = ret.decode().strip().split(' ')
            if len(ret)>1:
                ret = ''.join(ret[1:])
                ret = ret.split(',')
            else:
                ret = ret[0].split(',')
            self._scpi_version = ret[3].replace('"','').split('.')
            self._scpi_version = (int(self._scpi_version[0]), int(self._scpi_version[1]))
        else:
            return False
        
    def reset(self):
        self._sendRaw('*RST')
        
    def headersOff(self):
        """
        Deactivate Headers on response
        """
        self._sendRaw(':COMM:HEAD OFF')
        self._headersActive = False
        
    def setRate(self, rate=500):
        """Sets the Aggregation Rate of the measurement device
        
        This Function sets the aggregation rate (mean value) to the 
        specified value in milliseconds
        
        Args:
            rate (int): interval in milliseconds
                
        Returns:
            Nothing
        """
        
        ret = self._sendRaw(':RATE {:d}ms'.format(rate))
        if ret:
            return True
        else:
            return False
        
    def loadSetup(self, setupName):
        """Loads the specified setup on the measurement device
        
        This Function loads the specified measurement setup (.dms) on 
        the measurement device
        
        Args:
            setupName (str): Name or absolute path of the .dms file
                
        Returns:
            Nothing
        """
        ret = self._sendRaw(':SETUP:LOAD "{:s}"'.format(setupName))
        if ret:
            return True
        else:
            return False
        
    def setTransferChannels(self, channelNames, includeRelTime=False, includeAbsTime=False):
        """Sets the channels to be transfered within the numeric system
        
        This Function sets the channels to be transfered. This list must
        contain Oxygen channel names.
        
        Args:
            channelNames (list of str): List of channel names
                
        Returns:
            True if Suceeded, False if not
        """
        if includeRelTime:
            channelNames.insert(0, "REL-TIME")
        if includeAbsTime:
            channelNames.insert(0, "ABS-TIME")
        channelListStr = '"'+'","'.join(channelNames)+'"'
        ret = self._sendRaw(':NUM:NORMAL:ITEMS {:s}'.format(channelListStr))
        # Read back actual set channel names
        ret = self._askRaw(':NUM:NORMAL:ITEMS?')
        if isinstance(ret, bytes):
            ret = ret.decode().strip()
            ret = ret.replace(':NUM:ITEMS ','')
            channelNames = ret.split('","')
            channelNames = [chName.replace('"','') for chName in channelNames]
            if len(channelNames) == 1:
                log.debug('One Channel Set: {:s}'.format(channelNames[0]))
                if channelNames[0] == 'NONE':
                    channelNames = []
                    log.warn('No Channel Set')
            self.channelList = channelNames
            ret = self.setNumberChannels()
            if not ret:
                return False
            if isMinimumVersion(self._scpi_version, (1,6)):
                ret = self.getValueDimensions()
                if ret:
                    return True
                else:
                    return False
            return True
        else:
            return False

    def setNumberChannels(self, number=None):
        if number is None:
            number = len(self.channelList)
        ret = self._sendRaw(':NUM:NORMAL:NUMBER {:d}'.format(number))
        if ret:
            return True
        else:
            return False
        
    def getValueDimensions(self):
        """ Read the Dimension of the output 
        Available since 1.6
        """
        ret = self._askRaw(':NUM:NORM:DIMS?')
        if isinstance(ret, bytes):
            dim = ret.decode()
            if ' ' in dim:
                dim = dim.split(' ')[1]
            dim = dim.split(',')
            try:
                self._value_dimension = [int(d) for d in dim]
            except TypeError:
                self._value_dimension = False
                return False
            return True
        return False
    
    def setValueMaxDimensions(self):
        if self.getValueDimensions():
            for idx in range(len(self._value_dimension)):
                ret = self._sendRaw(':NUM:NORMAL:DIM{:d} MAX'.format(idx+1))
        else:
            return False
        if self.getValueDimensions():
            return True
        else:
            return False
                
        
    def getValues(self):
        """Queries the actual values from the numeric system
        
        This Function queries the actual values from the channels defined in
        setTransferChannels.
        
        Args:
            None
        Returns:
            List of values (list)
        """
        try:
            data = self._askRaw(':NUM:NORM:VAL?')
        except OSError:
            return False
        if type(data) is bytes:
            data = data.decode()
        else:
            # No Data Available or Wrong Channel
            return False
        # Remove Header if Whitespace present
        if ' ' in data:
            data = data.split(' ')[1]
        data = data.split(',')
        values = []
        if self._value_dimension is not None:
            idx = 0
            for dim in self._value_dimension:
                if dim < 2:
                    try:
                        values.append(float(data[idx]))
                        idx += 1
                        continue
                    except ValueError:
                        pass
                    except IndexError:
                        return False
                    try:
                        # Try to Parse DateTime "2017-10-10T12:16:52.33136+02:00"
                        # Variable lenght of Sub-Seconds
                        iso_ts = ''.join(data[idx].replace('"','').rsplit(':', 1))
                        ts = dt.datetime.strptime(iso_ts, '%Y-%m-%dT%H:%M:%S.%f%z')
                        values.append(ts)
                    except ValueError:
                        values.append(data[idx])
                    idx += 1
                else:
                    values.append([float(val) for val in data[idx:idx+dim]])        
                    idx += dim
        else:
            for val in data:
                try:
                    values.append(float(val))
                    continue
                except ValueError:
                    pass
                try:
                    # Try to Parse DateTime "2017-10-10T12:16:52.33136+02:00"
                    # Variable lenght of Sub-Seconds
                    iso_ts = ''.join(val.replace('"','').rsplit(':', 1))
                    ts = dt.datetime.strptime(iso_ts, '%Y-%m-%dT%H:%M:%S.%f%z')
                    values.append(ts)
                except ValueError as e:
                    values.append(val)
                    
        return values
    
    def storeSetFileName(self, fileName):
        """Sets the file name for the subsequent storing (recording) action
        
        This Function sets the file name for the subsequent storing action.
        The file will be stored in the default measurement folder on the device.
        
        Args:
            File Name (str)
        Returns:
            Status (bool)
        """
        try:
            state = self._sendRaw(':STOR:FILE:NAME "{:s}"'.format(fileName))
            return state
        except OSError:
            return False
        
    def storeStart(self):
        """Starts the storing (recording) action or resumes if it was paused.
        
        This Function starts the storing action or resumes if it was paused
        The data will be stored in the file previous set with setStoreFileName.
        
        Args:
            None
        Returns:
            Status (bool)
        """
        try:
            state = self._sendRaw(':STOR:START')
            return state
        except OSError:
            return False
        
    def storePause(self):
        """Pauses the storing (recording) action if it was started before.
        
        This Function pauses the storing action.
        
        Args:
            None
        Returns:
            Status (bool)
        """
        try:
            state = self._sendRaw(':STOR:PAUSE')
            return state
        except OSError:
            return False
        
    def storeStop(self):
        """Stops the storing (recording) action if it was started before.
        
        This Function stops the storing action. The data file is now finished
        and can be used for analysis now.
        
        Args:
            None
        Returns:
            Status (bool)
        """
        try:
            state = self._sendRaw(':STOR:STOP')
            return state
        except OSError:
            return False
        
    def getErrorSingle(self):
        """Query the first item in the error queue.
        
        This Function queries the first item in the error queue (oldest one)
        
        Args:
            None
        Returns:
            Error Message (str)
        """
        try:
            errorStr = self._askRaw(':SYST:ERR?')
            return errorStr
        except OSError:
            return False
        
    def lockScreen(self, lockState=True):
        if lockState:
            ret = self._sendRaw('SYST:KLOCK ON')
        else:
            ret = self._sendRaw('SYST:KLOCK OFF')
        if ret:
            return True
        else:
            return False
        
    def startAcquisition(self):
        try:
            state = self._sendRaw(':ACQU:START')
            return state
        except OSError:
            return False
        
    def stopAcquisition(self):
        try:
            state = self._sendRaw(':ACQU:STOP')
            return state
        except OSError:
            return False
        
    def restartAcquisition(self):
        try:
            state = self._sendRaw(':ACQU:RESTART')
            return state
        except OSError:
            return False
        
    def setElogChannels(self, channelNames):
        """Sets the channels to be transfered within the ELOG system
        
        This Function sets the channels to be transfered. This list must
        contain Oxygen channel names.
        
        Args:
            channelNames (list of str): List of channel names
                
        Returns:
            True if Suceeded, False if not
        """
        if not isMinimumVersion(self._scpi_version, (1,7)):
            log.warn('SCPI Version 1.7 or higher required')
            return False
            
        channelListStr = '"'+'","'.join(channelNames)+'"'
        ret = self._sendRaw(':ELOG:ITEMS {:s}'.format(channelListStr))
        sleep(0.1)
        # Read back actual set channel names
        ret = self._askRaw(':ELOG:ITEMS?')
        if isinstance(ret, bytes):
            ret = ret.decode().strip()
            ret = ret.replace(':ELOG:ITEM ','')
            channelNames = ret.split('","')
            channelNames = [chName.replace('"','') for chName in channelNames]
            if len(channelNames) == 1:
                log.debug('One Channel Set: {:s}'.format(channelNames[0]))
                if channelNames[0] == 'NONE':
                    channelNames = []
                    log.warn('No Channel Set')
            self.elogChannelList = channelNames
            if len(channelNames) == 0:
                return False
            else:
                return True
        else:
            return False 
    
    def startElog(self):
        ret = self._sendRaw(':ELOG:START')
        if ret:
            return True
        else:
            return False
        
    def setElogPeriod(self, period):
        ret = self._sendRaw(':ELOG:PERIOD {:f}'.format(period))
        if ret:
            return True
        else:
            return False
        
    def stopElog(self):
        ret = self._sendRaw(':ELOG:STOP')
        if ret:
            return True
        else:
            return False
        
    def setElogTimestamp(self, tsType='REL'):
        if tsType == 'REL':
            ret = self._sendRaw(':ELOG:TIM REL')
        elif tsType == 'ABS':
            ret = self._sendRaw(':ELOG:TIM ABS')
        else:
            ret = self._sendRaw(':ELOG:TIM OFF')
        if ret:
            return True
        else:
            return False
    
    def fetchElog(self):
        data = self._askRaw(':ELOG:FETCH?')
        if type(data) is bytes:
            data = data.decode()
        else:
            return False
        if 'NONE' in data:
            return False
        # Remove Header if Whitespace present
        if ' ' in data:
            data = data.split(' ')[1]
        data = data.split(',')
        numCh = len(self.elogChannelList)+1
        #print(len(data)/(1.0*numCh), data)
        numItems = int(len(data)/numCh)
        data = [data[i*numCh:i*numCh+numCh] for i in range(numItems)]
        return data
    
    def addMarker(self, label, description=None, time=None):
        if description is None and time is None:
            ret = self._sendRaw(':MARK:ADD "{:s}"'.format(label))
        elif description is None:
            ret = self._sendRaw(':MARK:ADD "{:s}",{:f}'.format(label, time))
        elif time is None:
            ret = self._sendRaw(':MARK:ADD "{:s}","{:s}"'.format(label, description))
        else:
            ret = self._sendRaw(':MARK:ADD "{:s}","{:s}",{:f}'.format(label, description, time))
        if ret:
            return True
        else:
            return False
    
# TODO: Better add and remove data stream instances            
class OxygenScpiDataStream(object):
    def __init__(self, oxygen):
        self.oxygen = oxygen
        
    def setItems(self, channelNames, streamGroup=1):
        """ Set Datastream Items to be transfered
        """
        if not isMinimumVersion(self.oxygen._scpi_version, (1,7)):
            log.warn('SCPI Version 1.7 or higher required')
            return False
        channelListStr = '"'+'","'.join(channelNames)+'"'
        ret = self.oxygen._sendRaw(':DST:ITEM{:d} {:s}'.format(streamGroup, channelListStr))
        sleep(0.1)
        # Read back actual set channel names
        ret = self.oxygen._askRaw(':DST:ITEM{:d}?'.format(streamGroup))
        if isinstance(ret, bytes):
            ret = ret.decode().strip()
            ret = ret.replace(':DST:ITEM{:d} '.format(streamGroup),'')
            channelNames = ret.split('","')
            channelNames = [chName.replace('"','') for chName in channelNames]
            if len(channelNames) == 1:
                log.debug('One Channel Set: {:s}'.format(channelNames[0]))
                if channelNames[0] == 'NONE':
                    channelNames = []
                    log.warn('No Channel Set')
            self.ChannelList = channelNames
            if len(channelNames) == 0:
                return False
            else:
                return True
        else:
            return False
        
    def setTcpPort(self, tcp_port, streamGroup=1):
        self.oxygen._sendRaw(':DST:PORT{:d} {:d}'.format(streamGroup, tcp_port))
        return True
        
    def init(self, streamGroup=1):
        if streamGroup == 'all':
            self.oxygen._sendRaw(':DST:INIT {:s}'.format(streamGroup))
        elif type(streamGroup) == int:
            self.oxygen._sendRaw(':DST:INIT {:d}'.format(streamGroup))
        else:
            return False
        return True
    
    def start(self, streamGroup=1):
        if streamGroup == 'all':
            self.oxygen._sendRaw(':DST:START ALL'.format(streamGroup))
        elif type(streamGroup) == int:
            self.oxygen._sendRaw(':DST:START {:d}'.format(streamGroup))
        else:
            return False
        return True
    
    def stop(self, streamGroup=1):
        if streamGroup == 'all':
            self.oxygen._sendRaw(':DST:STOP ALL'.format(streamGroup))
        elif type(streamGroup) == int:
            self.oxygen._sendRaw(':DST:STOP {:d}'.format(streamGroup))
        else:
            return False
        return True
    
    def getState(self, streamGroup=1):
        ret = self.oxygen._askRaw(':DST:STAT{:d}?'.format(streamGroup))
        if isinstance(ret, bytes):
            ret = ret.decode().strip()
            ret = ret.replace(':DST:STAT ','')
            return ret
        else:
            return False
        
    def reset(self):
        self.oxygen._sendRaw(':DST:RESET')