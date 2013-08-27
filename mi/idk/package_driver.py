"""
@file coi-services/mi.idk/package_driver.py
@author Bill French
@brief Main script class for running the package_driver process
"""

import sys
import os.path
import zipfile

import yaml

from mi.core.log import get_logger ; log = get_logger()
from mi.idk import prompt
from mi.idk.metadata import Metadata
from mi.idk.nose_test import NoseTest
from mi.idk.driver_generator import DriverGenerator
from mi.idk.egg_generator import EggGenerator

class PackageManifest(object):
    """
    Object to create and store a package file manifest
    """

    ###
    #   Configuration
    ###
    def manifest_file(self):
        return "file.lst"

    def manifest_path(self):
        return "%s/%s" % (self.metadata.idk_dir(), self.manifest_file())

    ###
    #   Public Methods
    ###
    def __init__(self, metadata):
        """
        @brief ctor
        """
        self.metadata = metadata
        self.data = {}

    def add_file(self, source, description=None):
        """
        @brief Add a file to the file manifest
        @param source path the the file in the archive
        @description one line description of the file
        """

        if(not description): description = ''

        log.debug( "  ++ Adding " + source + " to manifest")
        self.data[source] = description

        self.save()

    def serialize(self):
        """
        @brief Serialize PackageManifest object data into a yaml string.
        @retval yaml string
        """
        return yaml.dump( self.data, default_flow_style=False )

    def save(self):
        """
        @brief Write YAML file with package manifest.
        """
        outputFile = self.manifest_path()

        if not os.path.exists(self.metadata.idk_dir()):
            os.makedirs(self.metadata.idk_dir())

        ofile = open( outputFile, 'w' )

        ofile.write( self.serialize() )
        ofile.close()


class PackageDriver(object):
    """
    Main class for running the package driver process.
    """

    ###
    #   Configuration
    ###
    def string_file(self):
        return "strings.yml"
    
    def log_file(self):
        return "qualification.log"

    def log_path(self):
        return "%s/%s" % (self.metadata.idk_dir(), self.log_file())

    def archive_file(self):
        return "%s_%s_%s-%s-driver.zip" % (self.metadata.driver_make,
                                                      self.metadata.driver_model,
                                                      self.metadata.driver_name,
                                                      self.metadata.version)
    def archive_path(self):
        return os.path.join(os.path.expanduser("~"),self.archive_file())
    
    ###
    #   Public Methods
    ###
    def __init__(self):
        """
        @brief ctor
        """
        self.metadata = Metadata()
        self._zipfile = None
        self._manifest = None
        self._compression = None
        self.generator = DriverGenerator(self.metadata)

        # Set compression level
        self.zipfile_compression()

    def run_qualification_tests(self):
        """
        @brief Run all qualification tests for the driver and store the results for packaging
        """
        log.info("-- Running qualification tests")

        test = NoseTest(self.metadata, log_file=self.log_path())
        test.report_header()

        if(test.run_qualification()):
            log.info(" ++ Qualification tests passed")
            return True
        else:
            log.error("Qualification tests have fail!  No package created.")
            return False

    def package_driver(self):
        """
        @brief Store driver files in a zip package
        """
        log.info("-- Building driver package")
        self._store_package_files()

    def run(self):
        print "*** Starting Driver Packaging Process***"
        
        if len(sys.argv) == 2 and (sys.argv[1] == "--no-test"):
            # clear the log file so it exists
            f = open(self.log_path(), "w")
            f.write("Tests manually bypassed with --no-test option\n")
            f.close()
            self.package_driver()
        else:
            if(self.run_qualification_tests()):
                self.package_driver()

        print "Package Created: " + self.archive_path()

    def zipfile(self):
        """
        @brief Return the ZipFile object.  Create the file if it isn't already open
        @retval ZipFile object
        """
        if(not self._zipfile):
            self._zipfile = zipfile.ZipFile(self.archive_path(), mode="w")

        return self._zipfile

    def zipfile_compression(self):
        """
        @brief What type of compression should we use for the package file.  If we have access to zlib, we will compress
        @retval Compression type
        """

        if(self._compression): return self._compression

        try:
            import zlib
            self._compression = zipfile.ZIP_DEFLATED
            log.info("Setting compression level to deflated")
        except:
            log.info("Setting compression level to store only")
            self._compression = zipfile.ZIP_STORED

    def manifest(self):
        """
        @brief Return the PackageManifest object.  Create it if it doesn't already exist
        @retval PackageManifest object
        """
        if(not self._manifest):
            self._manifest = PackageManifest(self.metadata)

        return self._manifest


    ###
    #   Private Methods
    ###
    def _store_package_files(self):
        """
        @brief Store all files in zip archive and add them to the manifest file
        """

        egg_generator = EggGenerator(self.metadata)
        egg_file = egg_generator.save()

        # Add egg
        self._add_file(egg_file, 'egg', 'python driver egg package')

        # Add the package metadata file
        self._add_file(self.metadata.metadata_path(), description = 'package metadata')

        # Add the qualification test log
        self._add_file(self.log_path(), description = 'qualification tests results')

        # Store parameter/command string description file
        str_path = "%s/%s" % (self.generator.resource_dir(), self.string_file())
        if os.path.exists(str_path):
            self._add_file(str_path, 'resource', 'driver string file')
        
        # Store additional resource files
        self._store_resource_files()

        # Finally save the manifest file.  This must be last of course
        self._add_file(self.manifest().manifest_path(), description = 'package manifest file')


    def _store_resource_files(self):
        """
        @brief Store additional files added by the driver developer.  These
        files live in the driver resource dir.
        """
        resource_dir = self.generator.resource_dir()
        log.debug(" -- Searching for developer added resource files in dir: %s",
                  resource_dir)
        stringfile = self.string_file()
        if os.path.exists(resource_dir):
            for file in os.listdir(resource_dir):
                if file != stringfile:
                    log.debug("    ++ found: " + file)
                    desc = prompt.text('Describe ' + file)
                    self._add_file(resource_dir + "/" + file, 'resource', desc)
        else:
            log.debug(" --- No resource directory found, skipping...")

    def _add_file(self, source, destdir=None, description=None):
        """
        @brief Add a file to the zip package and store the file in the manifest.
        """
        filename = os.path.basename(source)
        dest = filename
        if(destdir):
            dest = "%s/%s" % (destdir, filename)

        log.debug("archive %s to %s" % (filename, dest))

        self.manifest().add_file(dest, description);
        self.zipfile().write(source, dest, self.zipfile_compression())


if __name__ == '__main__':
    app = PackageDriver()
    app.run()
