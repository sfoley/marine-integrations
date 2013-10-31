#!/usr/bin/env python

"""
@file coi-services/mi/idk/result_set.py
@author Bill French
@brief Read a result set file and use the data to verify
data particles.

Usage:

from mi.core.log import log

rs = ResultSet(result_set_file_path)
if not rs.verify(particles):
    log.info("Particle verified")
else:
    log.error("Particle validate failed")
    log.error(rs.report())

Result Set File Format:
  result files are yml formatted files with a header and data section.
  the data is stored in record elements with the key being the parameter name.
     - two special fields are internal_timestamp and _index.

eg.

# Result data for verifying particles. Comments are ignored.

header:
  particle_object: CtdpfParserDataParticleKey
  particle_type: ctdpf_parsed

data:
  -  _index: 1
     _new_sequence: True
     internal_timestamp: 07/26/2013 21:01:03
     temperature: 4.1870
     conductivity: 10.5914
     pressure: 161.06
     oxygen: 2693.0
  -  _index: 2
     internal_timestamp: 07/26/2013 21:01:04
     temperature: 4.1872
     conductivity: 10.5414
     pressure: 161.16
     oxygen: 2693.1

New sequence flag indicates that we are at the beginning of a new sequence of
contiguous records.
"""

__author__ = 'Bill French'
__license__ = 'Apache 2.0'

import os
import re
import yaml
import time
import ntplib
import datetime
from dateutil import parser
from dateutil import tz

import mi.core.common
from mi.core.instrument.data_particle import DataParticle

from mi.core.log import get_logger ; log = get_logger()

DATE_PATTERN = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$'
DATE_MATCHER = re.compile(DATE_PATTERN)

class ResultSet(object):
    """
    Result Set object
    Read result set files and compare to parsed particles.
    """
    def __init__(self, result_file_path):
        self.yaml = dict()

        log.debug("read result file: %s" % result_file_path)
        stream = file(result_file_path, 'r')
        result_set = yaml.load(stream)

        self._set_result_set(result_set)

        self._clear_report()

    def verify(self, particles):
        """
        Verify particles passed in against result set read
        in the ctor.

        Ensure:
          - Verify particles as a set
          - Verify individual particle data

        store verification result in the object and
        return success or failure.
        @param particls: list of particles to verify.
        @return True if verification successful, False otherwise
        """
        self._clear_report()
        result = True

        if self._verify_set(particles):
            result = self._verify_particles(particles)
        else:
            result = False

        if not result:
            log.error("Failed verification: \n%s", self.report())

        return result

    def report(self):
        """
        Return an ascii formatted verification failure report.
        @return string report
        """
        if len(self._report):
            return "\n".join(self._report)
        else:
            return None

    ###
    #   Helpers
    ###
    def _add_to_report(self, messages, indent = 0):
        """
        Add a message to the report buffer, pass an indent factor to
        indent message in the ascii report.
        """
        if not isinstance(messages, list): messages = [messages]

        for message in messages:
            ind = ""
            for i in range(0, indent):
                ind += "    "
            self._report.append("%s%s" %(ind, message))
            log.warn(message)

    def _clear_report(self):
        """
        Add a message to the report buffer, pass an indent factor to
        indent message in the ascii report.
        """
        self._report = []

    def _set_result_set(self, result_set):
        """
        Take data from yaml file and store it in internal objects for
        verifying data.  Raise an exception on error.
        """
        log.trace("Parsing result set header: %s", result_set)

        self._result_set_header = result_set.get("header")
        if not self._result_set_header: raise IOError("Missing result set header")
        log.trace("Header: %s", self._result_set_header)

        if self._result_set_header.get("particle_object") is None:
            IOError("header.particle_object not defined")

        if self._result_set_header.get("particle_type") is None:
            IOError("header.particle_type not defined")

        self._result_set_data = {}
        data = result_set.get("data")
        if not data: raise IOError("Missing result set data")

        for particle in data:
            index = particle.get("_index")
            if index is None:
                log.error("Particle definition missing _index: %s", particle)
                raise IOError("Particle definition missing _index")

            if self._result_set_data.get(index) is not None:
                log.error("Duplicate particle definition for _index %s: %s", index, particle)
                raise IOError("Duplicate definition found for index: %s"% index)

            self._result_set_data[index] = particle
            log.trace("Result set data: %s", self._result_set_data)

    def _verify_set(self, particles):
        """
        Verify the particles as a set match what we expect.
        - All particles are of the expected type
        - Check particle count
        """
        errors = []

        if len(self._result_set_data) != len(particles):
            errors.append("result set records != particles to verify (%d != %d)" %
                          (len(self._result_set_data), len(particles)))

        for particle in particles:
            if not self._verify_particle_type(particle):
                log.error("particle type mismatch: %s", particle)
                errors.append('particle type mismatch')

        if len(errors):
            self._add_to_report("Header verification failure")
            self._add_to_report(errors, 1)
            log.debug("Result set verify encountered errors: %s", errors)
            return False

        return True

    def _verify_particles(self, particles):
        """
        Verify data in the particles individually.
        - Verify order based on _index
        - Verify parameter data values
        - Verify there are extra or missing parameters
        """
        result = True
        index = 1
        for particle in particles:
            particle_def = self._result_set_data.get(index)
            errors = []

            # No particle definition, we fail
            if particle_def is None:
                errors.append("no particle result defined for index %d" % index)

            # Otherwise lets do some validation
            else:
                errors += self._get_particle_header_errors(particle, particle_def)
                errors += self._get_particle_data_errors(particle, particle_def)

            if len(errors):
                self._add_to_report("Failed particle validation for index %d" % index)
                self._add_to_report(errors, 1)
                result = False

            index += 1

        return result

    def _verify_particle_type(self, particle):
        """
        Verify that the object is a DataParticle and is the
        correct type.
        """
        if isinstance(particle, dict):
            return True

        expected = self._result_set_header['particle_object']
        cls = particle.__class__.__name__

        if not issubclass(particle.__class__, DataParticle):
            log.error("type not a data particle")

        if expected != cls:
            log.error("type mismatch: %s != %s", expected, cls)
            return False

        return True

    def _get_particle_header_errors(self, particle, particle_def):
        """
        Verify all parameters defined in the header:
        - Stream type
        - Internal timestamp
        """
        errors = []
        particle_dict = self._particle_as_dict(particle)
        particle_timestamp = particle_dict.get('internal_timestamp')
        expected_time = particle_def.get('internal_timestamp')

        # Verify the timestamp
        if particle_timestamp and not expected_time:
            errors.append("particle_timestamp defined in particle, but not expected")
        elif not particle_timestamp and expected_time:
            errors.append("particle_timestamp expected, but not defined in particle")

        # If we have a timestamp AND expect one then compare values
        elif (particle_timestamp and
              particle_timestamp != self._string_to_ntp_date_time(expected_time)):
            errors.append("expected internal_timestamp mismatch, %f != %f (%f)" %
                (self._string_to_ntp_date_time(expected_time), particle_timestamp,
                 self._string_to_ntp_date_time(expected_time)- particle_timestamp))

        # verify the stream name
        particle_stream = particle_dict['stream_name']
        expected_stream =  self._result_set_header['particle_type']
        if particle_stream != expected_stream:
            errors.append("expected stream name mismatch: %s != %s" %
                          (expected_stream, particle_stream))

        return errors

    def _get_particle_data_errors(self, particle, particle_def):
        """
        Verify that all data parameters are present and have the
        expected value
        """
        errors = []
        particle_dict = self._particle_as_dict(particle)
        log.debug("Particle to test: %s", particle_dict)
        log.debug("Particle definition: %s", particle_def)
        particle_values = particle_dict['values']

        expected_new_sequence = particle_dict.get("new_sequence", False)
        particle_new_sequence = particle_def.get("_new_sequence", False)
        if expected_new_sequence is None: expected_new_sequence = False
        if particle_new_sequence is None: particle_new_sequence = False

        if expected_new_sequence != particle_new_sequence:
            errors.append("New sequence flag mismatch, expected: %s, received: %s" %
                          (expected_new_sequence, particle_new_sequence))

        expected_keys = []
        for (key, value) in particle_def.items():
            if(key not in ['_index', '_new_sequence', 'internal_timestamp']):
                expected_keys.append(key)

        particle_keys = []
        pv = {}
        for value in particle_values:
            particle_keys.append(value['value_id'])
            pv[value['value_id']] = value['value']

        log.debug("Expected keys: %s", sorted(expected_keys))
        log.debug("Particle keys: %s", sorted(particle_keys))

        if sorted(expected_keys) != sorted(particle_keys):
            errors.append("expected / particle keys mismatch: %s != %s" %
                          (sorted(expected_keys), sorted(particle_keys)))

        else:
            for key in expected_keys:
                expected_value = particle_def[key]
                particle_value = pv[key]
                if expected_value != particle_value:
                    errors.append("%s value mismatch, %s != %s (decimals may be rounded)" % (key, expected_value, particle_value))



        return errors

    def _string_to_ntp_date_time(self, datestr):
        """
        Extract a date tuple from a formatted date string.
        @param str a string containing date information
        @retval a date tuple.
        @throws InstrumentParameterException if datestr cannot be formatted to
        a date.
        """
        if not isinstance(datestr, str):
            raise IOError('Value %s is not a string.' % str(datestr))
        try:
            localtime_offset = self._parse_time("1970-01-01T00:00:00.00")
            converted_time = self._parse_time(datestr)
            adjusted_time = converted_time - localtime_offset
            timestamp = ntplib.system_to_ntp_time(adjusted_time)

        except ValueError as e:
            raise ValueError('Value %s could not be formatted to a date. %s' % (str(datestr), e))

        log.debug("converting time string '%s', unix_ts: %s ntp: %s", datestr, adjusted_time, timestamp)

        return timestamp

    def _parse_time(self, datestr):
        if not DATE_MATCHER.match(datestr):
            raise ValueError("date string not in ISO8601 format YYYY-MM-DDTHH:MM:SS.SSSSZ")
        else:
            log.debug("Match: %s", datestr)

        if datestr[-1:] != 'Z':
            datestr += 'Z'

        log.debug("Converting time string: %s", datestr)
        dt = parser.parse(datestr)
        elapse = float(dt.strftime("%s.%f"))
        return elapse

    def _particle_as_dict(self, particle):
        if isinstance(particle, dict):
            return particle

        return particle.generate_dict()
