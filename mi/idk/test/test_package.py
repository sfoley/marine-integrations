#!/usr/bin/env python

"""
@package mi.idk.test.test_package
@file mi.idk/test/test_package.py
@author Bill French
@brief test file package process
"""

__author__ = 'Bill French'
__license__ = 'Apache 2.0'

import sys
import pkg_resources

from shutil import rmtree
from os.path import basename, dirname
from os import makedirs, path, remove
from os.path import exists
from zipfile import ZipFile
from shutil import copyfile

from nose.plugins.attrib import attr
from mock import Mock
import unittest
from mi.core.unit_test import MiUnitTest
from time import sleep

from mi.core.log import get_logger ; log = get_logger()
#from mi.core.log import log
from mi.idk.metadata import Metadata
from mi.idk.driver_generator import DriverGenerator

from mi.idk.exceptions import NotPython
from mi.idk.exceptions import NoRoot
from mi.idk.exceptions import FileNotFound
from mi.idk.exceptions import ValidationFailure

from mi.idk.config import Config
from mi.idk.egg_generator import DriverFileList
from mi.idk.egg_generator import DependencyList
from mi.idk.egg_generator import EggGenerator


ROOTDIR="/tmp/test_package.idk_test"
# /tmp is a link on OS X
if exists("/private/tmp"):
    ROOTDIR = "/private%s" % ROOTDIR
TESTDIR="%s/mi/foo" % ROOTDIR
TESTBASEDIR="%s/mi" % ROOTDIR


@attr('UNIT', group='mi')
class IDKPackageNose(MiUnitTest):
    """
    Base class for IDK Package Tests
    """    
    def setUp(self):
        """
        Setup the test case
        """
        # Our test path needs to be in the python path for SnakeFood to work.
        sys.path = ["%s/../.." % TESTDIR] + sys.path
        
        self.write_basefile()
        self.write_implfile()
        self.write_nosefile()
        self.write_resfile()
            
    def write_basefile(self):
        """
        Create all of the base python modules.  These files live in the same root
        and should be reported as internal dependencies
        """
        
        destdir = dirname(self.basefile())
        if not exists(destdir):
            makedirs(destdir)
        
        ofile = open(self.basefile(), "w")
        ofile.write( "class MiFoo():\n")
        ofile.write( "    def __init__():\n")
        ofile.write( "        pass\n\n")
        ofile.close()
        
        # base2.py is a simple python module with no dependencies
        initfile = self.basefile().replace("base.py", 'base2.py')
        ofile = open(initfile, "w")
        ofile.write( "import mi.base4\n")
        ofile.close()

        # base3.py has an external dependency
        initfile = self.basefile().replace("base.py", 'base3.py')
        ofile = open(initfile, "w")
        ofile.write( "import string\n\n")
        ofile.close()

        # base4.py has an circular dependency
        initfile = self.basefile().replace("base.py", 'base4.py')
        ofile = open(initfile, "w")
        ofile.write( "import base2\n\n")
        ofile.close()
        
        # We need out init file
        initfile = self.basefile().replace("base.py", '__init__.py')
        ofile = open(initfile, "w")
        ofile.write("")
        ofile.close()
        
    def write_implfile(self):
        """
        The impl.py file is the target of our test.  All tests will report the
        dependencies of this file.
        """
        destdir = dirname(self.implfile())
        if not exists(destdir):
            makedirs(destdir)
        
        # Write a base file
        ofile = open(self.implfile(), "w")
        
        # Test various forms of import. MiFoo is a class defined in base.py
        # The rest are py file imports.
        ofile.write( "from mi.base import MiFoo\n")
        ofile.write( "import mi.base2\n")
        ofile.write( "from mi import base3\n\n")
        ofile.close()
        
        # Add a pyc file to ignore
        initfile = self.implfile().replace("impl.py", 'impl.pyc')
        ofile = open(initfile, "w")
        ofile.close()
        
        # Ensure we have an import in an __init__ py file
        initfile = self.implfile().replace("impl.py", '__init__.py')
        ofile = open(initfile, "w")
        ofile.close()
        
    def write_nosefile(self):
        """
        The test.py file is the target of our test.  All tests will report the
        dependencies of this file.
        """
        destdir = dirname(self.nosefile())
        if not exists(destdir):
            makedirs(destdir)
        
        # Write a base test file
        ofile = open(self.nosefile(), "w")
        ofile.close()

        # Ensure we have an import in an __init__ py file
        initfile = self.nosefile().replace("test_process.py", '__init__.py')
        ofile = open(initfile, "w")
        ofile.close()

    def write_resfile(self):
        """
        The impl.py file is the target of our test.  All tests will report the
        dependencies of this file.
        """
        destdir = dirname(self.resfile())
        #log.debug(self.resfile())
        if not exists(destdir):
            makedirs(destdir)
        
        # Write a base file
        ofile = open(self.resfile(), "w")
        
        # Test various forms of import. MiFoo is a class defined in base.py
        # The rest are py file imports.
        ofile.write( "hello world\n")
        ofile.close()

    def basefile(self):
        """
        The main base python file imported by the target file.
        """
        return "%s/%s" % (TESTBASEDIR, "base.py")
        
    def implfile(self):
        """
        The main python we will target for the tests
        """
        return "%s/%s" % (TESTDIR, "impl.py")
        
    def nosefile(self):
        """
        The main test python we will target for the tests
        """
        return "%s/%s" % (TESTDIR, "test/test_process.py")
        
    def resfile(self):
        """
        The main test resource we will target for the tests
        """
        return "%s/%s" % (TESTDIR, "res/test_file")


@attr('UNIT', group='mi')
class TestDependencyList(IDKPackageNose):
    """
    Test the DependencyList object that uses the snakefood module.  
    """    
    def test_exceptions(self):
        """
        Test all of the failure states for DependencyList
        """
        generator = None
        try:
            generator = DependencyList("this_file_does_not_exist.foo")
        except FileNotFound, e:
            self.assertTrue(e)
        self.assertFalse(generator)
        
        generator = None
        try:
            generator = DependencyList("/etc/hosts")
        except NotPython, e:
            self.assertTrue(e)
        self.assertFalse(generator)
        
        
    def test_internal_dependencies(self):
        """
        Test internal the dependency lists.  This should include
        all of the files we created in setUp()
        """
        generator = DependencyList(self.implfile())
        root_list = generator.internal_roots()
        dep_list = generator.internal_dependencies()
            
        self.assertTrue(ROOTDIR in root_list)
        
        internal_deps = [
                          "mi/base.py", 
                          "mi/base2.py", 
                          "mi/base3.py",
                          "mi/base4.py",
                          "mi/foo/impl.py",
                        ]
            
        self.assertEqual(internal_deps, dep_list)
        
    def test_internal_dependencies_with_init(self):
        """
        Test internal the dependency lists.  This should include
        all of the files we created in setUp()
        """
        generator = DependencyList(self.implfile(), include_internal_init = True)
        root_list = generator.internal_roots()
        dep_list = generator.internal_dependencies()
        
        self.assertTrue(ROOTDIR in root_list)
        
        internal_deps = [
                          "mi/__init__.py",
                          "mi/base.py", 
                          "mi/base2.py", 
                          "mi/base3.py",
                          "mi/base4.py",
                          "mi/foo/__init__.py",
                          "mi/foo/impl.py", 
                         ]
        
        self.assertEqual(internal_deps, dep_list)

    def test_internal_test_dependencies_with_init(self):
        """
        Test internal the dependency lists for the unit test.
        """
        generator = DependencyList(self.nosefile(), include_internal_init = True)
        root_list = generator.internal_roots()
        dep_list = generator.internal_dependencies()

        self.assertTrue(ROOTDIR in root_list)

        internal_deps = [
            "mi/__init__.py",
            "mi/foo/__init__.py",
            "mi/foo/test/__init__.py",
            "mi/foo/test/test_process.py",
            ]

        self.assertEqual(internal_deps, dep_list)


    def test_external_dependencies(self):
        """
        Test external the dependency lists.  This should exclude
        all of the files we created in setUp()
        """
        generator = DependencyList(self.implfile())
        root_list = generator.external_roots()
        dep_list = generator.external_dependencies()
        
        self.assertFalse(ROOTDIR in root_list)

        self.assertFalse("mi/base4.py" in dep_list)
        self.assertFalse("mi/base3.py" in dep_list)
        self.assertFalse("mi/base2.py" in dep_list)
        self.assertFalse("mi/foo/impl.py" in dep_list)
        self.assertFalse("mi/base.py" in dep_list)
        self.assertTrue("string.py" in dep_list)
        
    def test_all_dependencies(self):
        """
        Test the full dependency lists.  This should exclude
        all of the files we created in setUp()
        """
        generator = DependencyList(self.implfile())
        root_list = generator.all_roots()
        dep_list = generator.all_dependencies()
        
        self.assertTrue(ROOTDIR in root_list)
        
        self.assertTrue("mi/base4.py" in dep_list)
        self.assertTrue("mi/base3.py" in dep_list)
        self.assertTrue("mi/base2.py" in dep_list)
        self.assertTrue("mi/foo/impl.py" in dep_list)
        self.assertTrue("mi/base.py" in dep_list)
        self.assertTrue("string.py" in dep_list)


@attr('UNIT', group='mi')
class TestDriverFileList(IDKPackageNose):
    """
    Test the driver file list object.  The driver file list is what is
    stored in the driver egg
    """
    def test_extra_list(self):
        """
        Find all the files in the driver directory
        """
        rootdir = dirname(TESTDIR)
        filelist = DriverFileList(Metadata(), ROOTDIR, self.implfile(), self.nosefile())
        self.assertTrue(filelist)
        
        known_files = [
            '%s/res/test_file' % TESTDIR
        ]
        
        files = filelist._extra_files()

        #log.debug(sorted(files))
        #log.debug(sorted(known_files))

        self.assertEqual(sorted(files), sorted(known_files))
        
        
    def test_list(self):
        """
        Test the full file manifest
        """
        filelist = DriverFileList(Metadata(), ROOTDIR, self.implfile(), self.nosefile())
        self.assertTrue(filelist)

        known_files = [
                      'mi/__init__.py',
                      'mi/base.py',
                      'mi/base2.py',
                      'mi/base3.py',
                      'mi/base4.py',
                      'mi/foo/__init__.py',
                      'mi/foo/impl.py',
                      'mi/foo/res/test_file',
                      'mi/foo/test/__init__.py',
                      'mi/foo/test/test_process.py'
                      ]
        
        files = filelist.files()
        log.debug("*** Files: %s", files)

        self.assertEqual(sorted(files), sorted(known_files))

    @unittest.skip("skip until all baseclass work complete")
    def test_sbe37_list(self):
        metadata = Metadata('seabird', 'sbe37smb', 'ooicore')
        filelist = DriverFileList(metadata, Config().get('working_repo'))
        known_files = ['mi/instrument/seabird/sbe37smb/ooicore/comm_config.yml',
                       'mi/instrument/seabird/sbe37smb/ooicore/metadata.yml',
                       'mi/__init__.py',
                       'mi/core/__init__.py',
                       'mi/core/common.py',
                       'mi/core/exceptions.py',
                       'mi/core/instrument/__init__.py',
                       'mi/core/instrument/data_particle.py',
                       'mi/core/instrument/instrument_driver.py',
                       'mi/core/instrument/instrument_fsm.py',
                       'mi/core/instrument/instrument_protocol.py',
                       'mi/core/instrument/protocol_param_dict.py',
                       'mi/instrument/__init__.py',
                       'mi/instrument/seabird/__init__.py',
                       'mi/instrument/seabird/sbe37smb/__init__.py',
                       'mi/instrument/seabird/sbe37smb/ooicore/__init__.py',
                       'mi/instrument/seabird/sbe37smb/ooicore/driver.py',
                       'mi/core/instrument/driver_client.py',
                       'mi/core/instrument/driver_process.py',
                       'mi/core/instrument/zmq_driver_client.py',
                       'mi/core/instrument/zmq_driver_process.py',
                       'mi/idk/__init__.py',
                       'mi/idk/comm_config.py',
                       'mi/idk/common.py',
                       'mi/idk/config.py',
                       'mi/idk/exceptions.py',
                       'mi/idk/prompt.py',
                       'mi/core/log.py',
                       'mi/core/tcp_client.py',
                       'mi/core/unit_test.py',
                       'mi/idk/util.py',
                       'mi/idk/instrument_agent_client.py',
                       'mi/core/instrument/port_agent_client.py',
                       'mi/core/instrument/logger_client.py',
                       'mi/idk/unit_test.py',
                       'mi/instrument/seabird/sbe37smb/ooicore/test/__init__.py',
                       'mi/instrument/seabird/sbe37smb/ooicore/test/test_driver.py']
        self.maxDiff = None
        files = filelist.files()
        log.debug("FILES = " + str(sorted(files)))
        self.assertEqual(sorted(files), sorted(known_files))

@attr('UNIT', group='mi')
class TestDriverEggGenerator(IDKPackageNose):
    """
    Test the egg generation process
    """
    def setUp(self):
        IDKPackageNose.setUp(self)

        self._repo_dir = Config().get('working_repo')
        self._tmp_dir  = Config().get('tmp_dir')

        self._metadata = Metadata('seabird', 'sbe37smb', 'ooicore', '.')
        self._generator = EggGenerator(self._metadata, self._repo_dir)

        # Ensure the base build dir doesnt exists
        build_dir = path.join(self._generator._tmp_dir(), self._generator._build_name())
        if exists(build_dir):
            rmtree(build_dir)
            self._generator._generate_build_dir()

    def tearDown(self):
        IDKPackageNose.tearDown(self)
        if exists(self._generator._build_dir()):
            rmtree(self._generator._build_dir())


    def test_path(self):
        """
        Test the object paths
        """
        known_name = "%s_%s_%s_%s" % (
            self._metadata.driver_make,
            self._metadata.driver_model,
            self._metadata.driver_name,
            self._metadata.version.replace('.', '_'),
            )

        self.assertEqual(self._generator._tmp_dir(), self._tmp_dir)
        self.assertEqual(self._generator._setup_path(), path.join(self._tmp_dir,self._generator._build_name(),'setup.py'))
        self.assertEqual(self._generator._build_name(), known_name)
        self.assertEqual(self._generator._build_dir(), path.join(self._tmp_dir,self._generator._build_name()))

    def test_build_dir_create(self):
        """
        test to ensure that the build dir is created properly
        """
        build_dir_orig = self._generator._generate_build_dir()
        self.assertFalse(exists(build_dir_orig))
        makedirs(build_dir_orig)
        self.assertTrue(exists(build_dir_orig))

        build_dir = self._generator._generate_build_dir()

        rmtree(build_dir_orig, True)
        self.assertFalse(exists(build_dir_orig))

        self.assertEqual(build_dir, build_dir_orig)


    def test_version_verify(self):
        with self.assertRaises(ValidationFailure):
            self._generator._verify_version(0)

        with self.assertRaises(ValidationFailure):
            self._generator._verify_version("5.1")

        with self.assertRaises(ValidationFailure):
            self._generator._verify_version(-1)

        with self.assertRaises(ValidationFailure):
            self._generator._verify_version("-1.1.1")

        self._generator._verify_version("1.1.1")


    def test_egg_build(self):
        '''
        Build an egg with some python source files.  Verify the
        egg was created properly and contains all expected files.
        @return:
        '''
        files = [ 'mi/__init__.py',
                  'mi/idk/__init__.py',
                  'mi/idk/config.py',
                  'res/config/mi-logging.yml',
                  'res/config/__init__.py',
                  'res/__init__.py'
        ]

        egg_files = [
            'EGG-INFO/dependency_links.txt',
            'EGG-INFO/entry_points.txt',
            'EGG-INFO/PKG-INFO',
            'EGG-INFO/requires.txt',
            'EGG-INFO/SOURCES.txt',
            'EGG-INFO/top_level.txt',
            'EGG-INFO/zip-safe',
            'mi/main.py',
        ]

        egg_file = self._generator._build_egg(files)
        self.assertTrue(exists(egg_file))

        # Verify that the files in the egg are what we expect.
        zipped = ZipFile(egg_file)

        # this files is actually moved to mi/mi-logging.yml and appears
        # in the egg_files list.
        #files.remove('res/config/mi-logging.yml')

        log.debug("EGG FILES: %s", sorted(zipped.namelist()))
        log.debug("EXP FILES: %s", sorted(files + egg_files))

        self.assertListEqual(sorted(zipped.namelist()), sorted(files + egg_files))

    def test_sbe37_egg(self):
        egg_file = self._generator.save()
        self.assertTrue(exists(egg_file))
