#!/usr/bin/python
#
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008, TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.
#

import sys
import multiprocessing

import urllib2
import bz2
import lzma

import piksemel

import pisi
import pisi.dependency as dependency
from pisi.graph import CycleException


class SourceDB:
    def __init__(self, index):

        self.__source_nodes = {}
        self.__pkgstosrc = {}

        doc = piksemel.parseString(index)
        self.__source_nodes, self.__pkgstosrc = self.__generate_sources(doc)

    def __generate_sources(self, doc):
        sources = {}
        pkgstosrc = {}

        for spec in doc.tags("SpecFile"):
            src_name = spec.getTag("Source").getTagData("Name")
            sources[src_name] = spec.toString()
            for package in spec.tags("Package"):
                pkgstosrc[package.getTagData("Name")] = src_name

        return sources, pkgstosrc

    def has_spec(self, name):
        return self.__source_nodes.has_key(name)

    def get_spec(self, name):
        src = self.__source_nodes[name]
        spec = pisi.specfile.SpecFile()
        spec.parse(src)
        return spec

    def get_source_uri(self, name):
        return self.get_spec(name).source.sourceURI

    def list_specs(self):
        return self.__source_nodes.keys()

    def get_source_uri_dict(self):
        return dict([(s, self.get_source_uri(s)) for s in self.__source_nodes.keys()])

    def get_uri_source_dict(self):
        return dict([(self.get_source_uri(s), s) for s in self.__source_nodes.keys()])
    
    def get_buid_dependencies(self, name):
        return self.get_spec(name).source.buildDependencies

    def pkgtosrc(self, name):
        return self.__pkgstosrc[name]

def find_circle(sourcedb, A):

    G_f = pisi.graph.Digraph()

    def get_spec(name):
        if sourcedb.has_spec(name):
            return sourcedb.get_spec(name)
        else:
            raise Exception('Cannot find source package: %s' % name)

    def get_src(name):
        return get_spec(name).source

    def add_src(src):
        if not str(src.name) in G_f.vertices():
            G_f.add_vertex(str(src.name), (src.version, src.release))

    def pkgtosrc(pkg):
        try:
            tmp = sourcedb.pkgtosrc(pkg)
        except KeyError, e:
            # this is a bad hack but after we hit a problem we need to continue
            tmp = "e3"
            print "---> borks in ", e

        return tmp

    B = A

    install_list = set()

    while len(B) > 0:
        Bp = set()
        for x in B:
            sf = get_spec(x)
            src = sf.source
            add_src(src)

            # add dependencies

            def process_dep(dep):
                srcdep = pkgtosrc(dep.package)
                if not srcdep in G_f.vertices():
                    Bp.add(srcdep)
                    add_src(get_src(srcdep))
                if not src.name == srcdep: # firefox - firefox-devel thing
                    G_f.add_edge(src.name, srcdep)

            for builddep in src.buildDependencies:
                process_dep(builddep)

#            for pkg in sf.packages:
#                for rtdep in pkg.packageDependencies:
#                    process_dep(rtdep)
        B = Bp

        try:
            order_build = G_f.topological_sort()
            order_build.reverse()
        except CycleException, cycle:
            return str(cycle)

    return ""

def getIndex(uri):
    try:
        if "://" in uri:
            rawdata = urllib2.urlopen(uri).read()
        else:
            rawdata = open(uri, "r").read()
    except IOError:
        print "could not fetch %s" % uri
        return None

    if uri.endswith("bz2"):
        data = bz2.decompress(rawdata)
    elif uri.endswith("xz") or uri.endswith("lzma"):
        data = lzma.decompress(rawdata)
    else:
        data = rawdata

    return data

def processPackage(pkg, sourcesLength, counter):
    global sourcedb

    sys.stdout.write("\r(%04d/%d) Calculating build dep of %s                       " % (counter, sourcesLength, pkg))
    sys.stdout.flush()

    return find_circle(sourcedb, [pkg])

def updateStatus(circleResult):
    global cycles
    cycles.add(circleResult)


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print "Usage: circlefinder.py <source repo pisi-index.xml file>"
        sys.exit(1)

    rawIndex = getIndex(sys.argv[1])
    sourcedb = SourceDB(rawIndex)
    sources = sourcedb.list_specs()

    sourcesLength = len(sources)
    counter = 0

    global cycles
    cycles = set()

    pool = multiprocessing.Pool()

    for pkg in sources:
        counter += 1
        pool.apply_async(processPackage, (pkg, sourcesLength, counter), callback=updateStatus)

    pool.close()
    pool.join()

    if len(cycles):
        print
        for cycle in cycles:
            print cycle
    else:
        print "No circular dep found"


