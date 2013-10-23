#!/usr/bin/env python

"""
@package mi.idk.test.test_config
@file mi.idk/test/test_config.py
@author Bill French
@brief test metadata object
"""

__author__ = 'Bill French'
__license__ = 'Apache 2.0'

from os import remove, makedirs
from os.path import exists
from shutil import rmtree, copyfile
import os

from nose.plugins.attrib import attr
from mock import Mock
import unittest
from mi.core.unit_test import MiUnitTest

from mi.core.log import get_logger ; log = get_logger()
from mi.idk.metadata import Metadata
from mi.idk.config import Config

from mi.idk.exceptions import DriverParameterUndefined
from mi.idk.exceptions import NoConfigFileSpecified
from mi.idk.exceptions import CommConfigReadFail
from mi.idk.exceptions import InvalidCommType

ROOTDIR="/tmp/test_config.idk_test"
# /tmp is a link on OS X
if exists("/private/tmp"):
    ROOTDIR = "/private%s" % ROOTDIR

@attr('UNIT', group='mi')
class TestConfig(MiUnitTest):
    """
    Test the config object.  
    """    
    def setUp(self):
        """
        Setup the test case
        """
        Config().cm.destroy()

        if not exists(ROOTDIR):
            makedirs(ROOTDIR)
          
        self.clear_config_file()
        
    def copy_config_file(self, src_file, dest_dir=ROOTDIR):
        """ On the test box, we wont always find an idk.yml file
        in the right place, so if there isnt one in in ROOTDIR,
        grab the one you found, then copy it to the ROOTDIR"""
        dest_file = self.config_file(dest_dir)
        if not os.path.exists(dest_file) and os.path.exists(src_file):
            log.debug("Copying config from %s to %s", src_file, dest_dir)
            copyfile(src_file, dest_file)
        
    def clear_config_file(self, dir=ROOTDIR):
        if exists(self.config_file(dir)):
            log.debug("remove test dir %s" % self.config_file())
            remove(self.config_file())
        self.assertFalse(exists(self.config_file()))

    def config_file(self, dir=ROOTDIR):
        return os.path.join(dir, "idk.yml")

    def read_config(self, cfgdir=ROOTDIR):
        cfgfile = self.config_file(cfgdir)
        infile = open(cfgfile, "r")
        result = infile.read()
        infile.close()
        return result

    def write_config(self, cfgdir=ROOTDIR):
        outfile = open(self.config_file(cfgdir), "a")
        outfile.write("  couchdb: couchdb\n")
        outfile.write("  start_couch: True\n")
        outfile.write("  start_rabbit: True\n")
        outfile.close()

    def test_default_config(self):
        """Test that the default configuration is created"""
        if os.path.exists(ROOTDIR):
            config = Config(ROOTDIR)
        else:
            self.copy_config_file(self.config_file(config.cm.config_dir))
            config = Config()
        #config = Config(ROOTDIR)
        self.assertTrue(config)

        expected_string = "idk:\n  start_couch: false\n  working_repo: %s\n  start_rabbit: false\n" % config.get("working_repo")


        #self.assertEqual(expected_string, self.read_config(config.cm.config_dir))
        log.debug("Config string: %s", self.read_config(config.cm.config_dir))
        self.assertTrue(config.get("working_repo"))
        self.assertTrue(config.get("template_dir"))
        self.assertTrue(config.get("couchdb"))
        self.assertTrue(config.get("rabbitmq"))
        self.assertTrue(False == config.get("start_rabbit"))
        self.assertTrue(False == config.get("start_couch"))

    def test_overloaded_config(self):
        """Test that the overloaded configuration"""
        # Build the default config and add a line
        if os.path.exists(ROOTDIR):
            config = Config(ROOTDIR)
        else:
            self.copy_config_file(self.config_file(config.cm.config_dir))
            config = Config()
        #config = Config(ROOTDIR)
        self.write_config(config.cm.config_dir)
        self.assertTrue(config)

        # reload the configuration
        config.cm.init(config.cm.config_dir)

        expected_string = "idk:\n  start_couch: false\n  working_repo: %s\n  start_rabbit: false\n  couchdb: %s\n  start_couch: True\n  start_rabbit: True\n" % (config.get("working_repo"), config.get("couchdb"))

        #self.assertEqual(expected_string, self.read_config(config.cm.config_dir))
        self.assertEqual(config.get("couchdb"), "couchdb")
        self.assertTrue(config.get("working_repo"))
        self.assertTrue(config.get("template_dir"))
        self.assertTrue(config.get("rabbitmq"))
        self.assertTrue(True == config.get("start_rabbit"))
        self.assertTrue(True == config.get("start_couch"))






