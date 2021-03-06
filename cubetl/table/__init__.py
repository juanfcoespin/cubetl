import logging
from os import listdir
from os.path import isfile, join
import itertools
import re
from cubetl.core import Node, Component
import chardet
from BeautifulSoup import UnicodeDammit
from cubetl.fs import FileReader
import csv
from abc import abstractmethod, ABCMeta
from cubetl.script import Eval
from cubetl.csv import CsvReader
from cubetl.core.exceptions import ETLException
import random


# Get an instance of a logger
logger = logging.getLogger(__name__)


class Table(Component):

    __metaclass__ = ABCMeta

    def lookup(self, ctx, attribs):

        if (len(attribs.keys()) == 0):
            raise Exception("Cannot lookup on table with no criteria (empty attribute set)")

        rows = self.find(ctx, attribs)
        rows = list(rows)
        if (len(rows) > 1):
            raise Exception("Found more than one row when searching for just one in %s: %s" % (self, attribs))
        elif (len(rows) == 1):
            row = rows[0]
        else:
            row = None
            #raise Exception("No rows found when looking up in %s: %s" % (self, attribs))

        logger.debug("Lookup result on %s: %s = %s" % (self, attribs, row))

        return row

    @abstractmethod
    def find(self, ctx, attribs):
        pass

    @abstractmethod
    def insert(self, ctx, attribs):
        pass

    @abstractmethod
    def update(self, ctx, attribs, lookup):
        pass

    @abstractmethod
    def upsert(self, ctx, attribs, lookup):
        pass

    @abstractmethod
    def delete(self, ctx, lookup):
        pass


class MemoryTable(Table):

    _rows = None

    def __init__(self):

        super(MemoryTable, self).__init__()

    def initialize(self, ctx):
        super(MemoryTable, self).initialize(ctx)
        if self._rows is None:
            self._rows = []


    def find(self, ctx, attribs):
        logger.debug("Searching %s in %s" % (attribs, self))
        for row in self._rows:
            match = True
            for key in attribs.keys():
                if (row[key] != attribs[key]):
                    match = False
                    break

            if (match):
                yield row


    def insert(self, ctx, attribs):
        if (ctx.debug2):
            logger.debug("Inserting %s in %s" % (attribs, self))
        # TODO: Copy?
        self._rows.append(attribs)

    def update(self, ctx, attribs, lookup):
        raise NotImplementedError()

    def upsert(self, ctx, attribs, lookup):
        raise NotImplementedError()

    def delete(self, ctx, lookup):
        raise NotImplementedError()


class ReadOnlyTable(Table):

    def insert(self, ctx, attribs):
        raise NotImplementedError("%s is a readonly table, cannot insert." % self)

    def update(self, ctx, attribs, lookup):
        raise NotImplementedError("%s is a readonly table, cannot be updated." % self)

    def upsert(self, ctx, attribs, lookup):
        raise NotImplementedError("%s is a readonly table, cannot upsert." % self)

    def delete(self, ctx, lookup):
        raise NotImplementedError("%s is a readonly table, cannot delete." % self)


class ProcessTable(ReadOnlyTable):

    process = None

    def __init__(self):

        super(ProcessTable, self).__init__()

    def initialize(self, ctx):
        super(ProcessTable, self).initialize(ctx)
        ctx.comp.initialize(self.process)

    def finalize(self, ctx):
        if self.process:
            ctx.comp.finalize(self.process)
        super(ProcessTable, self).finalize(ctx)

    def find(self, ctx, attribs):
        logger.debug("Process searching %s in %s" % (attribs, self))

        # Initialize message adding attributes
        message = ctx.copy_message(ctx.start_message)
        for key in attribs.keys():
            message[key] = attribs[key]

        # Run process
        msgs = ctx.comp.process(self.process, message)

        for row in msgs:
            yield row


class CsvMemoryTable(MemoryTable):
    """
    This component represents an in-memory table which can be defined in CSV format,
    which is handy to define in-line tables in the configuration files or to quickly read
    a CSV file in memory for lookups.

    The CSV data is processed by a CSVReader.

    Usage:

    """

    data = None  # Interpolated at initialization, no message available

    _csv_reader = None


    def initialize(self, ctx):
        """
        Reads CSV data on initialization.
        """

        super(CsvMemoryTable, self).initialize(ctx)

        self._csv_reader = CsvReader()
        self._csv_reader.data = ctx.interpolate(None, self.data)
        ctx.comp.initialize(self._csv_reader)

        for m in self._csv_reader.process(ctx, None):
            self.insert(ctx, m)

    def finalize(self, ctx):

        if self._csv_reader:
            ctx.comp.finalize(self._csv_reader)

        super(CsvMemoryTable, self).finalize(ctx)


class TableInsert(Node):

    def __init__(self):

        super(TableInsert, self).__init__()

        self.table = None
        self.mappings = None

    def initialize(self, ctx):

        super(TableInsert, self).initialize(ctx)
        ctx.comp.initialize(self.table)

    def finalize(self, ctx):

        ctx.comp.finalize(self.table)
        super(TableInsert, self).finalize(ctx)

    def process(self, ctx, m):

        # Process mappings
        attribs = {}
        for mapping in self.mappings:
            if "value" in mapping:
                attribs[mapping["name"]] = ctx.interpolate(m, mapping["value"])
            else:
                attribs[mapping["name"]] = m[mapping["name"]]

        # Store
        self.table.insert(ctx, attribs)

        yield m


class TableLookup(Node):

    table = None
    lookup = None
    default = None
    mappings = None

    def initialize(self, ctx):

        super(TableLookup, self).initialize(ctx)
        if not self.lookup: self.lookup = { }
        if not self.default: self.default = { }
        if not self.mappings: self.mappings = []

        ctx.comp.initialize(self.table)

    def finalize(self, ctx):

        ctx.comp.finalize(self.table)
        super(TableLookup, self).finalize(ctx)

    def _resolve_lookup_keys(self, ctx, m):

        if (not self.lookup):
            raise Exception("No lookup configuration defined for %s" % self)

        keys = {}
        for (key, expr) in self.lookup.items():
            keys[key] = ctx.interpolate(m, expr)

        return keys

    def _do_lookup(self, ctx, m, keys):
        result = self.table.lookup(ctx, keys)
        return result

    def process(self, ctx, m):

        keys = self._resolve_lookup_keys(ctx, m)

        result = self._do_lookup(ctx, m, keys)

        if (result):
            Eval.process_evals(ctx, m, self.mappings, result)
        else:
            m.update({ k: ctx.interpolate(m, v) for k, v in self.default.items() })

        yield m


class TableList(Node):

    table = None

    def initialize(self, ctx):

        super(TableList, self).initialize(ctx)
        ctx.comp.initialize(self.table)

    def finalize(self, ctx):
        ctx.comp.finalize(self.table)
        super(TableList, self).finalize(ctx)

    def _rowtodict(self, row):

        d = {}
        for column, value in row.items():
            d[column] = value

        return d

    def process(self, ctx, m):

        attribs = {}
        rows = self.table.find(ctx, attribs)
        for r in rows:

            m2 = ctx.copy_message(m)
            result = self._rowtodict(r)
            if (result != None):
                m2.update(result)

            yield m2


class TableRandomLookup(TableList):

    count = 1

    def process(self, ctx, m):

        attribs = {}
        rows = list(self.table.find(ctx, attribs))

        if len(rows) == 0:
            raise ETLException("Cannot draw a random items from an empty list (%s)" % self)

        for idx in range(self.count):
            m2 = ctx.copy_message(m)

            r = random.choice(rows)
            result = self._rowtodict(r)
            if (result != None):
                m2.update(result)

            yield m2
