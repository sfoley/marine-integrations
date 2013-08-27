"""
@package mi.instrument.sunburst.sami2_pco2.ooicore.driver
@file marine-integrations/mi/instrument/sunburst/sami2_pco2/ooicore/driver.py
@author Christopher Wingard
@brief Driver for the Sunburst Sensors, SAMI2-PCO2 (PCO2W)
Release notes:
    Sunburst Sensors SAMI2-PCO2 pCO2 underwater sensor.
    Derived from initial code developed by Chris Center,
    and merged with a base class covering both the PCO2W
    and PHSEN instrument classes.
"""

__author__ = 'Christopher Wingard'
__license__ = 'Apache 2.0'

import re

from mi.core.log import get_logger
log = get_logger()

from mi.core.exceptions import SampleException
from mi.core.exceptions import InstrumentProtocolException

from mi.core.common import BaseEnum
from mi.core.instrument.data_particle import DataParticle
from mi.core.instrument.data_particle import DataParticleKey
from mi.core.instrument.chunker import StringChunker
from mi.core.instrument.protocol_param_dict import ProtocolParameterDict
from mi.core.instrument.protocol_param_dict import ParameterDictType
from mi.core.instrument.protocol_param_dict import ParameterDictVisibility
from mi.instrument.sunburst.driver import SamiDataParticleType
from mi.instrument.sunburst.driver import ProtocolState
from mi.instrument.sunburst.driver import ProtocolEvent
from mi.instrument.sunburst.driver import Capability
from mi.instrument.sunburst.driver import SamiParameter
from mi.instrument.sunburst.driver import Prompt
from mi.instrument.sunburst.driver import SamiInstrumentCommand
from mi.instrument.sunburst.driver import SamiRegularStatusDataParticle
from mi.instrument.sunburst.driver import SamiRegularStatusDataParticleKey
from mi.instrument.sunburst.driver import SamiControlRecordDataParticle
from mi.instrument.sunburst.driver import SamiControlRecordDataParticleKey
from mi.instrument.sunburst.driver import SamiConfigDataParticleKey
from mi.instrument.sunburst.driver import SamiInstrumentDriver
from mi.instrument.sunburst.driver import SamiProtocol
from mi.instrument.sunburst.driver import REGULAR_STATUS_REGEX_MATCHER
from mi.instrument.sunburst.driver import CONTROL_RECORD_REGEX_MATCHER
from mi.instrument.sunburst.driver import ERROR_REGEX_MATCHER
from mi.instrument.sunburst.driver import NEWLINE
from mi.instrument.sunburst.driver import TIMEOUT
from mi.instrument.sunburst.driver import SAMI_TO_UNIX
from mi.instrument.sunburst.driver import SAMI_TO_NTP

###
#    Driver Constant Definitions
###

# Imported from base class

###
#    Driver RegEx Definitions
###

# Mostly defined in base class with these additional, instrument specfic
# additions

# SAMI Sample Records (Types 0x04 or 0x05)
SAMI_SAMPLE_REGEX = (
    r'[\*]' +  # record identifier
    '([0-9A-Fa-f]{2})' +  # unique instrument identifier
    '([0-9A-Fa-f]{2})' +  # length of data record (bytes)
    '(04|05)' +  # type of data record (04 for measurement, 05 for blank)
    '([0-9A-Fa-f]{8})' +  # timestamp (seconds since 1904)
    '([0-9A-Fa-f]{56})' +  # 14 sets of light measurements (counts)
    '([0-9A-Fa-f]{4})' +  # battery voltage (counts)
    '([0-9A-Fa-f]{4})' +  # thermistor (counts)
    '([0-9A-Fa-f]{2})' +  # checksum
    NEWLINE)
SAMI_SAMPLE_REGEX_MATCHER = re.compile(SAMI_SAMPLE_REGEX)

# Device 1 Sample Records (Type 0x11)
DEV1_SAMPLE_REGEX = (
    r'[\*]' +  #
    '([0-9A-Fa-f]{2})' +  # unique instrument identifier
    '([0-9A-Fa-f]{2})' +  # length of data record (bytes)
    '(11)' +  # type of data record (11 for external Device 1, aka the external pump)
    '([0-9A-Fa-f]{8})' +  # timestamp (seconds since 1904)
    '([0-9A-Fa-f]{2})' +  # checksum
    NEWLINE)
DEV1_SAMPLE_REGEX_MATCHER = re.compile(DEV1_SAMPLE_REGEX)

# PCO2W Configuration Record
CONFIGURATION_REGEX = (
    r'([0-9A-Fa-f]{8})' +  # Launch time timestamp (seconds since 1904)
    '([0-9A-Fa-f]{8})' +  # start time (seconds from launch time)
    '([0-9A-Fa-f]{8})' +  # stop time (seconds from start time)
    '([0-9A-Fa-f]{2})' +  # mode bit field
    '([0-9A-Fa-f]{6})' +  # Sami sampling interval (seconds)
    '([0-9A-Fa-f]{2})' +  # Sami driver type (0A)
    '([0-9A-Fa-f]{2})' +  # Pointer to Sami ph config parameters
    '([0-9A-Fa-f]{6})' +  # Device 1 interval
    '([0-9A-Fa-f]{2})' +  # Device 1 driver type
    '([0-9A-Fa-f]{2})' +  # Device 1 pointer to config params
    '([0-9A-Fa-f]{6})' +  # Device 2 interval
    '([0-9A-Fa-f]{2})' +  # Device 2 driver type
    '([0-9A-Fa-f]{2})' +  # Device 2 pointer to config params
    '([0-9A-Fa-f]{6})' +  # Device 3 interval
    '([0-9A-Fa-f]{2})' +  # Device 3 driver type
    '([0-9A-Fa-f]{2})' +  # Device 3 pointer to config params
    '([0-9A-Fa-f]{6})' +  # Prestart interval
    '([0-9A-Fa-f]{2})' +  # Prestart driver type
    '([0-9A-Fa-f]{2})' +  # Prestart pointer to config params
    '([0-9A-Fa-f]{2})' +  # Global config bit field
    '([0-9A-Fa-f]{2})' +  # pCO2-1: pump pulse duration
    '([0-9A-Fa-f]{2})' +  # pCO2-2: pump measurement duration
    '([0-9A-Fa-f]{2})' +  # pCO2-3: # samples per measurement
    '([0-9A-Fa-f]{2})' +  # pCO2-4: cycles between blanks
    '([0-9A-Fa-f]{2})' +  # pCO2-5: reagent cycles
    '([0-9A-Fa-f]{2})' +  # pCO2-6: blank cycles
    '([0-9A-Fa-f]{2})' +  # pCO2-7: flush pump interval
    '([0-9A-Fa-f]{2})' +  # pCO2-8: bit switches
    '([0-9A-Fa-f]{2})' +  # pCO2-9: extra pumps + cycle interval
    '([0-9A-Fa-f]{2})' +  # Device 1 (external pump) setting
    '([0-9A-Fa-f]{414})' +  # padding of 0's and then F's
    NEWLINE)
CONFIGURATION_REGEX_MATCHER = re.compile(CONFIGURATION_REGEX)


###
#    Begin Classes
###
class DataParticleType(SamiDataParticleType):
    """
    Data particle types produced by this driver
    """
    # PCO2W driver extends the base class (SamiDataParticleType) with:
    DEV1_SAMPLE = 'dev1_sample'


class Parameter(SamiParameter):
    """
    Device specific parameters.
    """
    # PCO2W driver extends the base class (SamiParameter) with:
    PUMP_PULSE = 'pump_pulse'
    PUMP_DURATION = 'pump_duration'
    SAMPLES_PER_MEASUREMENT = 'samples_per_measurement'
    CYCLES_BETWEEN_BLANKS = 'cycles_between_blanks'
    NUMBER_REAGENT_CYCLES = 'number_reagent_cycles'
    NUMBER_BLANK_CYCLES = 'number_blank_cycles'
    FLUSH_PUMP_INTERVAL = 'flush_pump_interval'
    BIT_SWITCHES = 'bit_switches'
    NUMBER_EXTRA_PUMP_CYCLES = 'number_extra_pump_cycles'
    EXTERNAL_PUMP_SETTINGS = 'external_pump_setting'


class InstrumentCommand(SamiInstrumentCommand):
    """
    Device specfic Instrument command strings. Extends superclass
    SamiInstrumentCommand
    """
    # PCO2W driver extends the base class (SamiInstrumentCommand) with:
    ACQUIRE_SAMPLE_DEV1 = 'R1'


###############################################################################
# Data Particles
###############################################################################
class Pco2wSamiSampleDataParticleKey(BaseEnum):
    """
    Data particle key for the SAMI2-PCO2 records. These particles
    capture when a sample was processed.
    """
    UNIQUE_ID = 'unique_id'
    RECORD_LENGTH = 'record_length'
    RECORD_TYPE = 'record_type'
    RECORD_TIME = 'record_time'
    LIGHT_MEASUREMENTS = 'light_measurements'
    VOLTAGE_BATTERY = 'voltage_battery'
    THERMISTER_RAW = 'thermistor_raw'
    CHECKSUM = 'checksum'


class Pco2wSamiSampleDataParticle(DataParticle):
    """
    Routines for parsing raw data into a SAMI2-PCO2 sample data particle
    structure.
    @throw SampleException If there is a problem with sample creation
    """
    _data_particle_type = DataParticleType.SAMI_SAMPLE

    def _build_parsed_values(self):
        """
        Parse SAMI2-PCO2 measurement records from raw data into a dictionary
        """

        ### SAMI Sample Record
        # Regular SAMI (PCO2) data records produced by the instrument on either
        # command or via an internal schedule. Like the control records, the
        # messages are preceded by a '*' character and terminated with a '\r'.
        # Sample string:
        #
        #   *542705CEE91CC800400019096206800730074C2CE04274003B0018096106800732074E0D82066124
        #
        # A full description of the data record strings can be found in the
        # vendor supplied SAMI Record Format document.
        ###

        matched = SAMI_SAMPLE_REGEX_MATCHER.match(self.raw_data)
        if not matched:
            raise SampleException("No regex match of parsed sample data: [%s]" %
                                  self.decoded_raw)

        particle_keys = [Pco2wSamiSampleDataParticleKey.UNIQUE_ID,
                         Pco2wSamiSampleDataParticleKey.RECORD_LENGTH,
                         Pco2wSamiSampleDataParticleKey.RECORD_TYPE,
                         Pco2wSamiSampleDataParticleKey.RECORD_TIME,
                         Pco2wSamiSampleDataParticleKey.LIGHT_MEASUREMENTS,
                         Pco2wSamiSampleDataParticleKey.VOLTAGE_BATTERY,
                         Pco2wSamiSampleDataParticleKey.THERMISTER_RAW,
                         Pco2wSamiSampleDataParticleKey.CHECKSUM]

        result = []
        grp_index = 1

        for key in particle_keys:
            if key in [Pco2wSamiSampleDataParticleKey.LIGHT_MEASUREMENTS]:
                # parse group 5 into 14, 2 byte (4 character) values stored in
                # an array.
                light = matched.group(grp_index)
                light = [int(light[i:i+4], 16) for i in range(0, len(light), 4)]
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: light})
            else:
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: int(matched.group(grp_index), 16)})
            grp_index += 1

        return result


class Pco2wDev1SampleDataParticleKey(BaseEnum):
    """
    Data particle key for the device 1 (external pump) records. These particles
    capture when a sample was collected.
    """
    UNIQUE_ID = 'unique_id'
    RECORD_LENGTH = 'record_length'
    RECORD_TYPE = 'record_type'
    RECORD_TIME = 'record_time'
    CHECKSUM = 'checksum'


class Pco2wDev1SampleDataParticle(DataParticle):
    """
    Routines for parsing raw data into a device 1 sample data particle
    structure.
    @throw SampleException If there is a problem with sample creation
    """
    _data_particle_type = DataParticleType.DEV1_SAMPLE

    def _build_parsed_values(self):
        """
        Parse device 1 values from raw data into a dictionary
        """

        ### Device 1 Sample Record (External Pump)
        # Device 1 data records produced by the instrument on either command or
        # via an internal schedule whenever the external pump is run (via the
        # R1 command). Like the control records and SAMI data, these messages
        # are preceded by a '*' character and terminated with a '\r'. Sample
        # string:
        #
        #   *540711CEE91DE2CE
        #
        # A full description of the device 1 data record strings can be found
        # in the vendor supplied SAMI Record Format document.
        ###

        matched = DEV1_SAMPLE_REGEX_MATCHER.match(self.raw_data)
        if not matched:
            raise SampleException("No regex match of parsed sample data: [%s]" %
                                  self.decoded_raw)

        particle_keys = [Pco2wDev1SampleDataParticleKey.UNIQUE_ID,
                         Pco2wDev1SampleDataParticleKey.RECORD_LENGTH,
                         Pco2wDev1SampleDataParticleKey.RECORD_TYPE,
                         Pco2wDev1SampleDataParticleKey.RECORD_TIME,
                         Pco2wDev1SampleDataParticleKey.CHECKSUM]

        result = []
        grp_index = 1

        for key in particle_keys:
            result.append({DataParticleKey.VALUE_ID: key,
                           DataParticleKey.VALUE: int(matched.group(grp_index), 16)})
            grp_index += 1
        return result


class Pco2wConfigurationDataParticleKey(SamiConfigDataParticleKey):
    """
    Data particle key for the configuration record.
    """
    PUMP_PULSE = 'pump_pulse'
    PUMP_DURATION = 'pump_duration'
    SAMPLES_PER_MEASUREMENT = 'samples_per_measurement'
    CYCLES_BETWEEN_BLANKS = 'cycles_between_blanks'
    NUMBER_REAGENT_CYCLES = 'number_reagent_cycles'
    NUMBER_BLANK_CYCLES = 'number_blank_cycles'
    FLUSH_PUMP_INTERVAL = 'flush_pump_interval'
    DISABLE_START_BLANK_FLUSH = 'disable_start_blank_flush'
    MEASURE_AFTER_PUMP_PULSE = 'measure_after_pump_pulse'
    NUMBER_EXTRA_PUMP_CYCLES = 'number_extra_pump_cycles'
    EXTERNAL_PUMP_SETTINGS = 'external_pump_setting'


class Pco2wConfigurationDataParticle(DataParticle):
    """
    Routines for parsing raw data into a configuration record data particle
    structure.
    @throw SampleException If there is a problem with sample creation
    """
    _data_particle_type = DataParticleType.CONFIGURATION

    def _build_parsed_values(self):
        """
        Parse configuration record values from raw data into a dictionary
        """

        ### SAMI-PCO2 Configuration String
        # Configuration string either sent to the instrument to configure it
        # (via the L5A command), or retrieved from the instrument in response
        # to the L command. Sample string (shown broken in multiple lines,
        # would not be received this way):
        #
        #   CEE90B0002C7EA0001E133800A000E100402000E10010B000000000D000000000D
        #   000000000D071020FF54181C010038140000000000000000000000000000000000
        #   000000000000000000000000000000000000000000000000000000000000000000
        #   000000000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #   FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #   FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #   FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #   FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        #
        # A full description of the configuration string can be found in the
        # vendor supplied Low Level Operation of the SAMI/AFT document.
        ###

        matched = CONFIGURATION_REGEX_MATCHER.match(self.raw_data)
        if not matched:
            raise SampleException("No regex match of parsed sample data: [%s]" %
                                  self.decoded_raw)

        particle_keys = [Pco2wConfigurationDataParticleKey.LAUNCH_TIME,
                         Pco2wConfigurationDataParticleKey.START_TIME_OFFSET,
                         Pco2wConfigurationDataParticleKey.RECORDING_TIME,
                         Pco2wConfigurationDataParticleKey.PMI_SAMPLE_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SAMI_SAMPLE_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT1_FOLLOWS_SAMI_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT1_INDEPENDENT_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT2_FOLLOWS_SAMI_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT2_INDEPENDENT_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT3_FOLLOWS_SAMI_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.SLOT3_INDEPENDENT_SCHEDULE,
                         Pco2wConfigurationDataParticleKey.TIMER_INTERVAL_SAMI,
                         Pco2wConfigurationDataParticleKey.DRIVER_ID_SAMI,
                         Pco2wConfigurationDataParticleKey.PARAMETER_POINTER_SAMI,
                         Pco2wConfigurationDataParticleKey.TIMER_INTERVAL_DEVICE1,
                         Pco2wConfigurationDataParticleKey.DRIVER_ID_DEVICE1,
                         Pco2wConfigurationDataParticleKey.PARAMETER_POINTER_DEVICE1,
                         Pco2wConfigurationDataParticleKey.TIMER_INTERVAL_DEVICE2,
                         Pco2wConfigurationDataParticleKey.DRIVER_ID_DEVICE2,
                         Pco2wConfigurationDataParticleKey.PARAMETER_POINTER_DEVICE2,
                         Pco2wConfigurationDataParticleKey.TIMER_INTERVAL_DEVICE3,
                         Pco2wConfigurationDataParticleKey.DRIVER_ID_DEVICE3,
                         Pco2wConfigurationDataParticleKey.PARAMETER_POINTER_DEVICE3,
                         Pco2wConfigurationDataParticleKey.TIMER_INTERVAL_PRESTART,
                         Pco2wConfigurationDataParticleKey.DRIVER_ID_PRESTART,
                         Pco2wConfigurationDataParticleKey.PARAMETER_POINTER_PRESTART,
                         Pco2wConfigurationDataParticleKey.USE_BAUD_RATE_57600,
                         Pco2wConfigurationDataParticleKey.SEND_RECORD_TYPE,
                         Pco2wConfigurationDataParticleKey.SEND_LIVE_RECORDS,
                         Pco2wConfigurationDataParticleKey.EXTEND_GLOBAL_CONFIG,
                         Pco2wConfigurationDataParticleKey.PUMP_PULSE,
                         Pco2wConfigurationDataParticleKey.PUMP_DURATION,
                         Pco2wConfigurationDataParticleKey.SAMPLES_PER_MEASUREMENT,
                         Pco2wConfigurationDataParticleKey.CYCLES_BETWEEN_BLANKS,
                         Pco2wConfigurationDataParticleKey.NUMBER_REAGENT_CYCLES,
                         Pco2wConfigurationDataParticleKey.NUMBER_BLANK_CYCLES,
                         Pco2wConfigurationDataParticleKey.FLUSH_PUMP_INTERVAL,
                         Pco2wConfigurationDataParticleKey.DISABLE_START_BLANK_FLUSH,
                         Pco2wConfigurationDataParticleKey.MEASURE_AFTER_PUMP_PULSE,
                         Pco2wConfigurationDataParticleKey.NUMBER_EXTRA_PUMP_CYCLES,
                         Pco2wConfigurationDataParticleKey.EXTERNAL_PUMP_SETTINGS]

        result = []
        grp_index = 1   # used to index through match groups, starting at 1
        mode_index = 0  # index through the bit fields for MODE_BITS,
                        # GLOBAL_CONFIGURATION and SAMI_BIT_SWITCHES.
        glbl_index = 0
        sami_index = 0

        for key in particle_keys:
            if key in [Pco2wConfigurationDataParticleKey.PMI_SAMPLE_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SAMI_SAMPLE_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT1_FOLLOWS_SAMI_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT1_INDEPENDENT_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT2_FOLLOWS_SAMI_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT2_INDEPENDENT_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT3_FOLLOWS_SAMI_SCHEDULE,
                       Pco2wConfigurationDataParticleKey.SLOT3_INDEPENDENT_SCHEDULE]:
                # if the keys match values represented by the bits in the one
                # byte mode bits value, parse bit-by-bit using the bit-shift
                # operator to determine the boolean value.
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: bool(int(matched.group(4), 16) & (1 << mode_index))})
                mode_index += 1  # bump the bit index
                grp_index = 5    # set the right group index for when we leave this part of the loop.

            elif key in [Pco2wConfigurationDataParticleKey.USE_BAUD_RATE_57600,
                         Pco2wConfigurationDataParticleKey.SEND_RECORD_TYPE,
                         Pco2wConfigurationDataParticleKey.SEND_LIVE_RECORDS,
                         Pco2wConfigurationDataParticleKey.EXTEND_GLOBAL_CONFIG]:
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: bool(int(matched.group(20), 16) & (1 << glbl_index))})

                glbl_index += 1  # bump the bit index
                # skip bit indices 3 through 6
                if glbl_index == 3:
                    glbl_index = 7
                grp_index = 21  # set the right group index for when we leave this part of the loop.

            elif key in [Pco2wConfigurationDataParticleKey.DISABLE_START_BLANK_FLUSH,
                         Pco2wConfigurationDataParticleKey.MEASURE_AFTER_PUMP_PULSE]:
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: bool(int(matched.group(28), 16) & (1 << sami_index))})
                sami_index += 1  # bump the bit index
                grp_index = 29   # set the right group index for when we leave this part of the loop.

            else:
                # otherwise all values in the string are parsed to integers
                result.append({DataParticleKey.VALUE_ID: key,
                               DataParticleKey.VALUE: int(matched.group(grp_index), 16)})
                grp_index += 1

        return result


###############################################################################
# Driver
###############################################################################
class InstrumentDriver(SamiInstrumentDriver):
    """
    InstrumentDriver subclass.
    Subclasses SamiInstrumentDriver and SingleConnectionInstrumentDriver with
    connection state machine.
    """
    ########################################################################
    # Superclass overrides for resource query.
    ########################################################################

    def get_resource_params(self):
        """
        Return list of device parameters available.
        """
        return Parameter.list()

    ########################################################################
    # Protocol builder.
    ########################################################################

    def _build_protocol(self):
        """
        Construct the driver protocol state machine.
        """
        self._protocol = Protocol(Prompt, NEWLINE, self._driver_event)


###########################################################################
# Protocol
###########################################################################
class Protocol(SamiProtocol):
    """
    Instrument protocol class
    Subclasses CommandResponseInstrumentProtocol
    """
    def __init__(self, prompts, newline, driver_event):
        """
        Protocol constructor.
        @param prompts A BaseEnum class containing instrument prompts.
        @param newline The newline.
        @param driver_event Driver process event callback.
        """
        # Construct protocol superclass.
        SamiProtocol.__init__(self, prompts, newline, driver_event)

        # Build protocol state machine.

        ###
        # most of these are defined in the base class with exception of handlers
        # defined below that differ for the two instruments (what defines
        # success and the timeout duration)
        ###

        # this state would be entered whenever an ACQUIRE_SAMPLE event occurred
        # while in the AUTOSAMPLE state and will last anywhere from a few
        # seconds to ~12 minutes depending on instrument and the type of
        # sampling.
        self._protocol_fsm.add_handler(ProtocolState.SCHEDULED_SAMPLE, ProtocolEvent.SUCCESS,
                                       self._handler_sample_success)
        self._protocol_fsm.add_handler(ProtocolState.SCHEDULED_SAMPLE, ProtocolEvent.TIMEOUT,
                                       self._handler_sample_timeout)

        # this state would be entered whenever an ACQUIRE_SAMPLE event occurred
        # while in either the COMMAND state (or via the discover transition
        # from the UNKNOWN state with the instrument unresponsive) and will
        # last anywhere from a few seconds to 3 minutes depending on instrument
        # and sample type.
        self._protocol_fsm.add_handler(ProtocolState.POLLED_SAMPLE, ProtocolEvent.SUCCESS,
                                       self._handler_sample_success)
        self._protocol_fsm.add_handler(ProtocolState.POLLED_SAMPLE, ProtocolEvent.TIMEOUT,
                                       self._handler_sample_timeout)

        # Add build handlers for device commands.
        ### primarily defined in base class
        self._add_build_handler(InstrumentCommand.ACQUIRE_SAMPLE_DEV1, self._build_sample_dev1)

        # Add response handlers for device commands.
        ### primarily defined in base class
        self._add_response_handler(InstrumentCommand.ACQUIRE_SAMPLE_DEV1, self._build_response_sample_dev1)

        # Add sample handlers

        # State state machine in UNKNOWN state.
        self._protocol_fsm.start(ProtocolState.UNKNOWN)

        # build the chunker
        self._chunker = StringChunker(Protocol.sieve_function)

    @staticmethod
    def sieve_function(raw_data):
        """
        The method that splits samples
        """
        return_list = []

        sieve_matchers = [REGULAR_STATUS_REGEX_MATCHER,
                          CONTROL_RECORD_REGEX_MATCHER,
                          SAMI_SAMPLE_REGEX_MATCHER,
                          DEV1_SAMPLE_REGEX_MATCHER,
                          CONFIGURATION_REGEX_MATCHER]

        for matcher in sieve_matchers:
            for match in matcher.finditer(raw_data):
                return_list.append((match.start(), match.end()))

        return return_list

    def _got_chunk(self, chunk, timestamp):
        """
        The base class got_data has gotten a chunk from the chunker. Pass it to
        extract_sample with the appropriate particle objects and REGEXes.
        """
        self._extract_sample(SamiRegularStatusDataParticle, REGULAR_STATUS_REGEX_MATCHER, chunk, timestamp)
        self._extract_sample(SamiControlRecordDataParticle, CONTROL_RECORD_REGEX_MATCHER, chunk, timestamp)
        self._extract_sample(Pco2wSamiSampleDataParticle, SAMI_SAMPLE_REGEX_MATCHER, chunk, timestamp)
        self._extract_sample(Pco2wDev1SampleDataParticle, DEV1_SAMPLE_REGEX_MATCHER, chunk, timestamp)
        self._extract_sample(Pco2wConfigurationDataParticle, CONFIGURATION_REGEX_MATCHER, chunk, timestamp)

    ########################################################################
    # Build Command, Driver and Parameter dictionaries
    ########################################################################

    def _build_param_dict(self):
        """
        For each parameter key, add match stirng, match lambda function,
        and value formatting function for set commands.
        """
        # Add parameter handlers to parameter dict.
        self._param_dict = ProtocolParameterDict()

        ### example configuration string
        # VALID_CONFIG_STRING = 'CEE90B0002C7EA0001E133800A000E100402000E10010B' + \
        #                       '000000000D000000000D000000000D07' + \
        #                       '1020FF54181C01003814' + \
        #                       '000000000000000000000000000000000000000000000000000' + \
        #                       '000000000000000000000000000000000000000000000000000' + \
        #                       '0000000000000000000000000000' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + \
        #                       'FFFFFFFFFFFFFFFFFFFFFFFFFFFFF' + NEWLINE
        #
        ###

        self._param_dict.add(Parameter.LAUNCH_TIME, CONFIGURATION_REGEX,
                             lambda match: int(match.group(1), 16),
                             lambda x: self._int_to_hexstring(x, 8),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00000000,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='launch time')

        self._param_dict.add(Parameter.START_TIME_FROM_LAUNCH, CONFIGURATION_REGEX,
                             lambda match: int(match.group(2), 16),
                             lambda x: self._int_to_hexstring(x, 8),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x02C7EA00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='start time after launch time')

        self._param_dict.add(Parameter.STOP_TIME_FROM_START, CONFIGURATION_REGEX,
                             lambda match: int(match.group(3), 16),
                             lambda x: self._int_to_hexstring(x, 8),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x01E13380,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='stop time after start time')

        self._param_dict.add(Parameter.MODE_BITS, CONFIGURATION_REGEX,
                             lambda match: int(match.group(4), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x0A,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='mode bits (set to 00001010)')

        self._param_dict.add(Parameter.SAMI_SAMPLE_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(5), 16),
                             lambda x: self._int_to_hexstring(x, 6),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x000E10,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='sami sample interval')

        self._param_dict.add(Parameter.SAMI_DRIVER_VERSION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(6), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x04,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='sami driver version')

        self._param_dict.add(Parameter.SAMI_PARAMS_POINTER, CONFIGURATION_REGEX,
                             lambda match: int(match.group(7), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x02,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='sami parameter pointer')

        self._param_dict.add(Parameter.DEVICE1_SAMPLE_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(8), 16),
                             lambda x: self._int_to_hexstring(x, 6),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x000E10,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 1 sample interval')

        self._param_dict.add(Parameter.DEVICE1_DRIVER_VERSION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(9), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x01,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 1 driver version')

        self._param_dict.add(Parameter.DEVICE1_PARAMS_POINTER, CONFIGURATION_REGEX,
                             lambda match: int(match.group(10), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x0B,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 1 parameter pointer')

        self._param_dict.add(Parameter.DEVICE2_SAMPLE_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(11), 16),
                             lambda x: self._int_to_hexstring(x, 6),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x000000,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 2 sample interval')

        self._param_dict.add(Parameter.DEVICE2_DRIVER_VERSION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(12), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 2 driver version')

        self._param_dict.add(Parameter.DEVICE2_PARAMS_POINTER, CONFIGURATION_REGEX,
                             lambda match: int(match.group(13), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x0D,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 2 parameter pointer')

        self._param_dict.add(Parameter.DEVICE3_SAMPLE_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(14), 16),
                             lambda x: self._int_to_hexstring(x, 6),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x000000,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 3 sample interval')

        self._param_dict.add(Parameter.DEVICE3_DRIVER_VERSION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(15), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 3 driver version')

        self._param_dict.add(Parameter.DEVICE3_PARAMS_POINTER, CONFIGURATION_REGEX,
                             lambda match: int(match.group(16), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x0D,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='device 3 parameter pointer')

        self._param_dict.add(Parameter.PRESTART_SAMPLE_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(17), 16),
                             lambda x: self._int_to_hexstring(x, 6),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x000000,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='prestart sample interval')

        self._param_dict.add(Parameter.PRESTART_DRIVER_VERSION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(18), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='prestart driver version')

        self._param_dict.add(Parameter.PRESTART_PARAMS_POINTER, CONFIGURATION_REGEX,
                             lambda match: int(match.group(19), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x0D,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='prestart parameter pointer')

        self._param_dict.add(Parameter.GLOBAL_CONFIGURATION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(20), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='global bits (set to 00000111)')

        self._param_dict.add(Parameter.PUMP_PULSE, CONFIGURATION_REGEX,
                             lambda match: int(match.group(21), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x10,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='pump pulse duration')

        self._param_dict.add(Parameter.PUMP_DURATION, CONFIGURATION_REGEX,
                             lambda match: int(match.group(22), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x20,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='pump measurement duration')

        self._param_dict.add(Parameter.SAMPLES_PER_MEASUREMENT, CONFIGURATION_REGEX,
                             lambda match: int(match.group(23), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0xFF,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='samples per measurement')

        self._param_dict.add(Parameter.CYCLES_BETWEEN_BLANKS, CONFIGURATION_REGEX,
                             lambda match: int(match.group(24), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0xA8,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='cycles between blanks')

        self._param_dict.add(Parameter.NUMBER_REAGENT_CYCLES, CONFIGURATION_REGEX,
                             lambda match: int(match.group(25), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x18,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='number of reagent cycles')

        self._param_dict.add(Parameter.NUMBER_BLANK_CYCLES, CONFIGURATION_REGEX,
                             lambda match: int(match.group(26), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x1C,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='number of blank cycles')

        self._param_dict.add(Parameter.FLUSH_PUMP_INTERVAL, CONFIGURATION_REGEX,
                             lambda match: int(match.group(27), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x01,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='flush pump interval')

        self._param_dict.add(Parameter.BIT_SWITCHES, CONFIGURATION_REGEX,
                             lambda match: int(match.group(28), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x00,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='bit switches')

        self._param_dict.add(Parameter.NUMBER_EXTRA_PUMP_CYCLES, CONFIGURATION_REGEX,
                             lambda match: int(match.group(29), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x38,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='number of extra pump cycles')

        self._param_dict.add(Parameter.EXTERNAL_PUMP_SETTINGS, CONFIGURATION_REGEX,
                             lambda match: int(match.group(30), 16),
                             lambda x: self._int_to_hexstring(x, 2),
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=True,
                             default_value=0x14,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name='external pump settings')

    #########################################################################
    ## General (for POLLED and SCHEDULED states) Sample handlers.
    #########################################################################

    def _handler_sample_success(self, *args, **kwargs):
        next_state = None
        result = None

        return (next_state, result)

    def _handler_sample_timeout(self, ):
        next_state = None
        result = None

        return (next_state, result)

    ########################################################################
    # Command handlers.
    ########################################################################
    def _build_sample_dev1(self):
        pass

    ########################################################################
    # Response handlers.
    ########################################################################
    def _build_response_sample_dev1(self):
        pass
