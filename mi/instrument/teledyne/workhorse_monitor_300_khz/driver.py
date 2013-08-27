"""
@package mi.instrument.teledyne.workhorse_monitor_300_khz.driver
@file marine-integrations/mi/instrument/teledyne/workhorse_monitor_300_khz/driver.py
@author Roger Unwin
@brief Driver for the 300khz family
Release notes:
"""

__author__ = 'Roger Unwin'
__license__ = 'Apache 2.0'

from mi.core.util import dict_equal

from mi.core.instrument.instrument_fsm import InstrumentFSM
from mi.core.instrument.instrument_driver import DriverEvent
from mi.instrument.teledyne.driver import TeledyneProtocol
from mi.instrument.teledyne.driver import TeledynePrompt
from mi.instrument.teledyne.driver import TeledyneParameter
from mi.instrument.teledyne.driver import TeledyneInstrumentCmds
from mi.instrument.teledyne.driver import TeledyneProtocolEvent
from mi.instrument.teledyne.driver import TeledyneProtocolState
from mi.instrument.teledyne.driver import TeledyneCapability
from mi.instrument.teledyne.driver import TeledyneInstrumentDriver
from mi.instrument.teledyne.driver import TeledyneScheduledJob

from mi.core.instrument.instrument_driver import DriverAsyncEvent

from mi.instrument.teledyne.workhorse_monitor_300_khz.particles import *

from mi.core.instrument.chunker import StringChunker

from mi.core.instrument.protocol_param_dict import ParameterDictVisibility
from mi.core.instrument.protocol_param_dict import ParameterDictType

class WorkhorsePrompt(TeledynePrompt):
    pass


class WorkhorseParameter(TeledyneParameter):
    """
    Device parameters
    """

    TIME_PER_BURST = 'TB'
    ENSEMBLES_PER_BURST = 'TC'
    BUFFER_OUTPUT_PERIOD = 'TX'
    SYNC_INTERVAL = "SI"
    SLAVE_TIMEOUT = "ST"
    SYNC_DELAY = "SW"
    BANNER = 'CH'
    SERIAL_FLOW_CONTROL = 'CF'
    SLEEP_ENABLE = 'CL'
    SAVE_NVRAM_TO_RECORDER = 'CN'
    POLLED_MODE = 'CP'
    #PITCH = 'EP'                        # Tilt 1 Sensor (1/100 deg) -6000 to 6000 (-60.00 to +60.00 degrees)
    #ROLL = 'ER'                         # Tilt 2 Sensor (1/100 deg) -6000 to 6000 (-60.00 to +60.00 degrees)

class WorkhorseInstrumentCmds(TeledyneInstrumentCmds):
    """
    """
    POWER_DOWN = 'CZ'


class WorkhorseProtocolEvent(TeledyneProtocolEvent):
    """
    """
    pass


class WorkhorseProtocolState(TeledyneProtocolState):
    pass


class WorkhorseCapability(TeledyneCapability):
    """
    """
    POWER_DOWN = WorkhorseProtocolEvent.POWER_DOWN


class WorkhorseScheduledJob(TeledyneScheduledJob):
    pass


###############################################################################
# Driver
###############################################################################

class WorkhorseInstrumentDriver(TeledyneInstrumentDriver):
    """
    InstrumentDriver subclass for Workhorse 75khz driver.
    Subclasses SingleConnectionInstrumentDriver with connection state
    machine.
    """
    def __init__(self, evt_callback):
        """
        InstrumentDriver constructor.
        @param evt_callback Driver process event callback.
        """
        #Construct superclass.
        TeledyneInstrumentDriver.__init__(self, evt_callback)

    ########################################################################
    # Protocol builder.
    ########################################################################

    def _build_protocol(self):
        """
        Construct the driver protocol state machine.
        """
        self._protocol = WorkhorseProtocol(TeledynePrompt, NEWLINE, self._driver_event)

###########################################################################
# Protocol
###########################################################################

class WorkhorseProtocol(TeledyneProtocol):
    """
    Instrument protocol class
    Subclasses CommandResponseInstrumentProtocol
    """

    @staticmethod
    def sieve_function(raw_data):
        """
        Chunker sieve method to help the chunker identify chunks.
        @returns a list of chunks identified, if any.
        The chunks are all the same type.
        """

        sieve_matchers = [ADCP_COMPASS_CALIBRATION_REGEX_MATCHER,
                          ADCP_SYSTEM_CONFIGURATION_REGEX_MATCHER,
                          ADCP_PD0_PARSED_REGEX_MATCHER]

        return_list = []

        for matcher in sieve_matchers:
            if matcher == ADCP_PD0_PARSED_REGEX_MATCHER:
                #
                # Have to cope with variable length binary records...
                # lets grab the length, then write a proper query to
                # snag it.
                #
                matcher2 = re.compile(r'\x7f\x7f(..)', re.DOTALL)
                for match in matcher2.finditer(raw_data):
                    l = unpack("H", match.group(1))
                    outer_pos = match.start()
                    ADCP_PD0_PARSED_TRUE_MATCHER = re.compile(r'\x7f\x7f(.{' + str(l[0]) + '})', re.DOTALL)
                    for match in ADCP_PD0_PARSED_TRUE_MATCHER.finditer(raw_data, outer_pos):
                        inner_pos = match.start()

                        if (outer_pos == inner_pos):
                            return_list.append((match.start(), match.end()))
            else:
                for match in matcher.finditer(raw_data):
                    return_list.append((match.start(), match.end()))
                    
        return return_list

    def __init__(self, prompts, newline, driver_event):
        """
        Protocol constructor.
        @param prompts A BaseEnum class containing instrument prompts.
        @param newline The newline.
        @param driver_event Driver process event callback.
        """
        log.trace("IN WorkhorseProtocol.__init__")
        # Construct protocol superclass.
        TeledyneProtocol.__init__(self, prompts, newline, driver_event)

        self._protocol_fsm.add_handler(WorkhorseProtocolState.COMMAND,
                                       WorkhorseProtocolEvent.POWER_DOWN,
                                       self._handler_command_power_down)

        self._chunker = StringChunker(WorkhorseProtocol.sieve_function)
        

    ########################################################################
    # Private helpers.
    ########################################################################

    def _get_params(self):
        return dir(WorkhorseParameter)

    def _getattr_key(self, attr):
        return getattr(WorkhorseParameter, attr)

    def _has_parameter(self, param):
        return WorkhorseParameter.has(param)

    def _build_command_dict(self):
        """
        Populate the command dictionary with command.
                self.cmd_dict.add("cmd1",
                          timeout=60,
                          display_name="Command 1",
                          description="Execute a foo on the instrument",
                          return_type="bool",
                          return_units="Success",
                          return_description="Success (true) or failure (false)",
                          arguments=[CommandArgument(
                                     name="coeff",
                                     required=True,
                                     display_name="coefficient",
                                     description="The coefficient to use for calculation",
                                     type=CommandDictType.FLOAT,
                                     value_description="Should be between 1.97 and 2.34"
                                     ),
                                     CommandArgument(
                                     name="delay",
                                     required=False,
                                     display_name="delay time",
                                     description="The delay time to wait before executing",
                                     type=CommandDictType.FLOAT,
                                     units="seconds",
                                     value_description="Should be between 1.0 and 3.3 in increments of 0.1"
                                     )
                                    ]
                         )

        """

        self._cmd_dict.add(WorkhorseCapability.START_AUTOSAMPLE,
                           timeout=300,
                           display_name="start autosample",
                           description="Place the instrument into autosample mode")
        self._cmd_dict.add(WorkhorseCapability.STOP_AUTOSAMPLE,
                           display_name="stop autosample",
                           description="Exit autosample mode and return to command mode")
        self._cmd_dict.add(WorkhorseCapability.CLOCK_SYNC,
                           display_name="sync clock")
        self._cmd_dict.add(WorkhorseCapability.GET_CALIBRATION,
                           display_name="get calibration")
        self._cmd_dict.add(WorkhorseCapability.GET_CONFIGURATION,
                           timeout=300,
                           display_name="get configuration")
        self._cmd_dict.add(WorkhorseCapability.GET_INSTRUMENT_TRANSFORM_MATRIX,
                           display_name="get instrument transform matrix")
        self._cmd_dict.add(WorkhorseCapability.SAVE_SETUP_TO_RAM,
                           display_name="save setup to ram")
        self._cmd_dict.add(WorkhorseCapability.SEND_LAST_SAMPLE,
                           display_name="send last sample")
        self._cmd_dict.add(WorkhorseCapability.GET_ERROR_STATUS_WORD,
                           display_name="get error status word")
        self._cmd_dict.add(WorkhorseCapability.CLEAR_ERROR_STATUS_WORD,
                           display_name="clear error status word")
        self._cmd_dict.add(WorkhorseCapability.GET_FAULT_LOG,
                           display_name="get fault log")
        self._cmd_dict.add(WorkhorseCapability.CLEAR_FAULT_LOG,
                           display_name="clear fault log")
        self._cmd_dict.add(WorkhorseCapability.RUN_TEST_200,
                           display_name="run test 200")
        self._cmd_dict.add(WorkhorseProtocolEvent.POWER_DOWN,   # <------ TODO bubble this up to base class.
                           display_name="Power Down")

    def _got_chunk(self, chunk, timestamp):
        """
        The base class got_data has gotten a chunk from the chunker.
        Pass it to extract_sample with the appropriate particle
        objects and REGEXes.
        """
        if (self._extract_sample(ADCP_COMPASS_CALIBRATION_DataParticle,
                                 ADCP_COMPASS_CALIBRATION_REGEX_MATCHER,
                                 chunk,
                                 timestamp)):
            log.debug("_got_chunk - successful match for ADCP_COMPASS_CALIBRATION_DataParticle")

        if (self._extract_sample(ADCP_SYSTEM_CONFIGURATION_DataParticle,
                                 ADCP_SYSTEM_CONFIGURATION_REGEX_MATCHER,
                                 chunk,
                                 timestamp)):
            log.debug("_got_chunk - successful match for ADCP_SYSTEM_CONFIGURATION_DataParticle")
        if (self._extract_sample(ADCP_PD0_PARSED_DataParticle,
                                 ADCP_PD0_PARSED_REGEX_MATCHER,
                                 chunk,
                                 timestamp)):
            log.debug("_got_chunk - successful match for ADCP_PD0_PARSED_DataParticle")
            if self.disable_autosample_recover != True:
                if (self._protocol_fsm.get_current_state() == WorkhorseProtocolState.COMMAND):
                    log.debug("FSM appears out of date.  Fixing it!")
                    self._protocol_fsm.on_event(WorkhorseProtocolEvent.RECOVER_AUTOSAMPLE)
                return



    def _filter_capabilities(self, events):
        """
        Return a list of currently available capabilities.
        """
        return [x for x in events if WorkhorseCapability.has(x)]

    def _handler_command_power_down(self):
        """
        """
        pass
