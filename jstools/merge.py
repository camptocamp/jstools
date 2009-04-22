"""
merge.py

Copyright (c) 2008 OpenGeo. All rights reserved.
"""

from ConfigParser import ConfigParser
from jstools import jsmin
from jstools import tsort
from StringIO import StringIO
import logging
import os
import pkg_resources
import re

DIST = pkg_resources.Requirement.parse("jstools")    
SUFFIX_JAVASCRIPT = ".js"
RE_REQUIRE = re.compile("@requires (.*)\n")
RE_INCLUDE = re.compile("@include (.*)\n")

DEP_LINE = re.compile("^// @[include|requires]")

special_section_prefixes = ["meta"]

_marker = object()


logger = logging.getLogger('jstools.merge')

class MissingImport(Exception):
    """Exception raised when a listed import is not found in the lib."""

class Merger(ConfigParser):
    def __init__(self, output_dir, defaults=None, printer=logger.info):
        ConfigParser.__init__(self, defaults)
        self.output_dir = output_dir
        self.printer = printer
        self.reverse_included = dict()
        
    @classmethod
    def from_fn(cls, fn, output_dir, defaults=None, printer=logger.info):
        """Load up a list of config filenames in our merger"""
        merger = cls(output_dir, defaults=defaults, printer=printer)
        if isinstance(fn, basestring):
            fn = fn,
        fns = merger.read(fn)
        assert fns, ValueError("No valid config files: %s" %fns)
        return merger

    @classmethod
    def from_resource(cls, resource_name, output_dir, dist=DIST, defaults=None, printer=logger.info):
        conf = pkg_resources.resource_stream(dist, resource_name)
        merger = cls(output_dir, defaults=defaults, printer=printer)
        merger.readfp(conf)
        return merger

    def make_sourcefile(self, sourcedir, filepath, exclude):
        self.printer("Importing: %s" % filepath)
        return SourceFile(sourcedir, filepath, exclude)
    
    def merge(self, cfg, depmap=None):
        #@@ this function needs to be decomposed into smaller testable bits
        sourcedir = cfg['root']

        # assemble all files in source directory according to config
        include = cfg.get('include', False)
        exclude = cfg['exclude']
        all_inc = (cfg['first'] + cfg['include'] + cfg['last'])
        files = dict((filepath, self.make_sourcefile(sourcedir, filepath, exclude)) \
                    for filepath in jsfiles_for_dir(sourcedir) \
                    if (include and filepath in all_inc or \
                        (not include and filepath not in exclude)))

        # ensure all @include and @requires references are in
        complete = False
        while not complete:
            complete = True
            for filepath, info in files.items():
                for path in info.include + info.requires:
                    if path not in cfg['exclude'] and not files.has_key(path):
                        complete = False
                        files[path] = self.make_sourcefile(sourcedir, path, exclude)
        
        # create list of dependencies
        dependencies = {}
        for filepath, info in files.items():
            dependencies[filepath] = info.requires

        
        # get tuple of files ordered by dependency
        self.printer("Sorting dependencies.")
        order = [x for x in tsort.sort(dependencies)]

        # move forced first and last files to the required position
        self.printer("Re-ordering files.")
        order = cfg['first'] + [item
                     for item in order
                     if ((item not in cfg['first']) and
                         (item not in cfg['last']))] + cfg['last']

        parts = ('first', 'include', 'last')
        required_files = []
        
        ## Make sure all imports are in files dictionary
        ## Create list of all required files for this part
        for part in parts:
            fps = cfg[part]
            required_files.extend(fps)
            for fp in fps:
                if not fp in cfg['exclude'] and not files.has_key(fp):
                    raise MissingImport("File from '%s' not found: %s" % (part, fp))
                required_files.extend(dependencies[fp])

        # filter out stray files that are not dependencies
        rmap = dict(zip(required_files, (True for x in range(len(required_files)))))
        order = [item for item in order if rmap.get(item)]
        
        ## Header inserted at the start of each file in the output
        HEADER = "/* " + "=" * 70 + "\n    %s\n" + "   " + "=" * 70 + " */\n\n"

        ## Output the files in the determined order
        result = []
        for fp in order:
            f = files[fp]
            self.printer("Exporting: " + f.filepath)
            result.append(HEADER % f.filepath)
            source = f.source
            result.append(source)
            if not source.endswith("\n"):
                result.append("\n")

        self.printer("\nTotal files merged: %d " % len(files))
        merged = "".join(result)
        if cfg['closure']:
            merged = '(function(){%s})();' % merged
        return merged

    key_list = 'include', 'exclude', 'last', 'first', 
    keys = 'license', 'root', 'closure',

    def make_cfg(self, section):
        cfg = dict(self.items(section))
        for key in self.key_list:
            val = cfg.setdefault(key, [])
            if isinstance(val, basestring):
                cfg[key]=[x for x in val.split() if not x.startswith('#')]
        for key in self.keys:
            cfg.setdefault(key, None)
        return cfg

    def strip_deps(self, merged):
        #@@ make optional?
        return "\n".join(x for x in merged.split('\n') if not DEP_LINE.match(x))

    def compress(self, merged, plugin="default"):
        self.printer("Compressing with %s" %plugin)
        dist = pkg_resources.get_distribution("jstools")
        ep_map = pkg_resources.get_entry_map(dist, "jstools.compressor")
        args = None
        try:
            plugin, args = plugin.split(":")
        except ValueError:
            pass
        func = ep_map.get(plugin).load()
        return func(merged, args)

    def do_section(self, section, cfg, uncompressed=False, concatenate=False, strip_deps=True):
        header = "Building %s" % section
        self.printer("%s\n%s" % (header, "-" * len(header)))
        merged = self.merge(cfg)
        if not uncompressed:
            merged = self.compress(merged)
        elif strip_deps:
            merged = self.strip_deps(merged)
            
        if cfg.has_key('output'):
            outputfilename = cfg['output']
        else:
            outputfilename = os.path.join(self.output_dir, section)

        if cfg['license']:
            self.printer("Adding license file: %s" %cfg['license'])
            merged = file(cfg['license']).read() + merged
        return outputfilename, merged

    def js_sections(self):
        raw_sections = self.sections()
        if self.has_section("meta"):
            #@@ will need overhaul as soon as meta gets used for anything else
            # order the stuff someone cares about
            order = self.get("meta", "order").split()
            sections = [raw_sections.pop(raw_sections.index(index)) for index in order]
            # don't leave anything behind
            sections.extend(raw_sections)
            sections.remove('meta')
            return sections
        return raw_sections

    def run(self, uncompressed=False, single=None, strip_deps=True, concatenate=None, compressor="default"):
        sections = self.js_sections()
        if single is not None:
            assert single in sections, ValueError("%s not in %s" %(single, sections))
            sections = [single]
            
        #@@ refactor into a function for cat and one for multiples
        newfiles = []
        cat = dict()
        for section in sections:
            cfg = self.make_cfg(section)
            if not concatenate:
                outputfilename, merged = self.do_section(section, cfg, uncompressed, strip_deps)
                self.printer("Writing to %s (%d KB).\n" % (outputfilename, int(len(merged) / 1024)))
                file(outputfilename, "w").write(merged)
            else:
                outputfilename, merged = self.do_section(section, cfg, True, strip_deps)
                cat[outputfilename] = merged
            newfiles.append(outputfilename)

        if concatenate:
            outputfilename = os.path.join(self.output_dir, concatenate)
            catted = StringIO()
            for name in newfiles:
                print >> catted, cat[name]
            if not uncompressed:
                self.compress(strip_deps, compressor)

            self.printer("Writing to %s (%d KB).\n" % (outputfilename, int(len(merged) / 1024)))
            sfb = file(outputfilename, "w").write(catted.getvalue())
            newfiles = [outputfilename]
            
        return newfiles


class SourceFile(object):
    """
    Represents a Javascript source code file.

    -- use depmap if given
    """

    def __init__(self, sourcedir, filepath, exclude, depmap=None):
        """
        """
        self.filepath = filepath
        self.exclude = exclude
        self.source = open(os.path.join(sourcedir, filepath), "U").read()
        self._requires = _marker
        self._include = _marker
        self.depmap = depmap

    @property
    def requires(self):
        """
        Extracts the dependencies specified in the source code and returns
        a list of them.
        """
        req = getattr(self, '_requires', None)
        if req is _marker:
            self._requires = [x for x in RE_REQUIRE.findall(self.source)\
                              if x not in self.exclude]
        return self._requires

    @property
    def include(self):
        """
        Extracts the list of files to be included before or after this one.
        """
        req = getattr(self, '_include', None)
        if req is _marker:
            self._include = [x for x in RE_INCLUDE.findall(self.source) \
                             if x not in self.exclude]
                                   
        return self._include

def jsfiles_for_dir(sourcedir, jssuffix=SUFFIX_JAVASCRIPT):
    for root, dirs, entries in os.walk(sourcedir):
        for filename in entries:
            if filename.endswith(jssuffix) and not filename.startswith("."):
                filepath = os.path.join(root, filename)[len(sourcedir)+1:]
                filepath = filepath.replace("\\", "/")
                yield filepath
