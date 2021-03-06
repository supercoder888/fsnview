#!/usr/bin/env python3

__version__ = "0.3.0" 

import argparse
import logging
import collections
import os
import sys

import Objects

_logger = logging.getLogger(os.path.basename(__file__))

class Summarizer(object):
    """
    Counts, for a single DFXML file:
    * Files
    * Partitions

    The counts are broken out by:
    * Files: allocation status (nullable)
    * Files: is a directory (nullable)
    """
    def __init__(self, xmlfile):
        self.volumes = set()

        #Key: (allocation status, name type) vector
        #Value: tally
        self.broken_out_files = collections.defaultdict(lambda: 0)

        self.failed = None
        try:
            for (event, obj) in Objects.iterparse(xmlfile):
                if isinstance(obj, Objects.VolumeObject):
                    _logger.debug("Found a volume in %r." % xmlfile)
                    self.volumes.add(obj)
                elif isinstance(obj, Objects.FileObject):
                    if obj.alloc_inode is None and obj.alloc_name is None:
                        alloc = obj.alloc
                    else:
                        alloc = obj.alloc_inode and obj.alloc_name
                    self.broken_out_files[(alloc, obj.name_type)] += 1
            self.failed = False
        except Exception as e:
            self.failed = True
            logging.debug("Exception encountered processing %r." % xmlfile)
            logging.debug(e)

def _safe_int(value):
    if value is None:
        return "."
    else:
        return str(value)

class SummarizerTabulator(object):
    def __init__(self):
        self._summarizers = dict()
        self._format_dict = None
        self._stats_dict = None

    def summarize(self, prog, xmlfile):
        s = Summarizer(xmlfile)
        self._summarizers[prog] = s

    def _get_format_dict(self):
        if self._format_dict:
            return self._format_dict

        format_dict = collections.defaultdict(lambda: str())
        format_dict["tool_count"] = len(self._summarizers)
        format_dict["latex_column_aligns"] = "|".join(["r"]*format_dict["tool_count"])
        format_dict["html_partial_colspan"] = format_dict["tool_count"] + 1
        for prog in sorted(self._summarizers.keys()):
            format_dict["latex_tool_column_headers"] += "& " + prog
            format_dict["html_tool_column_headers"] += "<th>" + prog + "</th>"

            for sf in ["s", "f"]:
                format_dict["latex_row_%s_parts_processed" % sf] += "& %(" + sf + "/volumes/" + prog + ")s "
                format_dict["html_row_%s_parts_processed" % sf] += "<td>%(" + sf + "/volumes/" + prog + ")s</td>"
                for ua in ["allocated", "unallocated", "unknown"]:
                    for df in ["dirs", "files", "unknown", "other"]:
                        format_dict["latex_row_%s_%s_%s" % (sf, ua, df)] += "& %(" + "/".join([sf, ua, df, prog]) + ")s "
                        format_dict["html_row_%s_%s_%s" % (sf, ua, df)] += "<td>%(" + "/".join([sf, ua, df, prog]) + ")s</td>"
        self._format_dict = format_dict
        #logging.debug("self._format_dict = %r" % self._format_dict)
        return self._format_dict

    def _get_stats_dict(self):
        if self._stats_dict:
            return self._stats_dict
        num_stats_dict = collections.defaultdict(lambda: 0)
        str_stats_dict = collections.defaultdict(lambda: "0")
        for prog in sorted(self._summarizers.keys()):
            summarizer = self._summarizers[prog]
            breakouts = self._summarizers[prog].broken_out_files
            sf = "f" if summarizer.failed else "s"

            num_stats_dict[sf + "/volumes/" + prog] = len(summarizer.volumes)

            for key in breakouts:
                alloc = key[0]
                name_type = key[1]

                #Build stats dictionary key
                if alloc is None:
                    ua = "unknown"
                else:
                    ua = "allocated" if alloc else "unallocated"

                if name_type is None:
                    df = "unknown"
                elif name_type == "d":
                    df = "dirs"
                elif name_type == "r":
                    df = "files"
                else:
                    df = "other"

                num_stats_dict["/".join([sf, ua, df, prog])] += breakouts[key]
        for key in num_stats_dict:
            str_stats_dict[key] = str(num_stats_dict[key])
        self._stats_dict = str_stats_dict
        #logging.debug("self._stats_dict = %r" % self._stats_dict)
        return self._stats_dict
        
    def write_html(self, fp):
        with open(fp, "w") as fh:
            format_dict = self._get_format_dict()
            stats_dict = self._get_stats_dict()

            template0 = """\
<!doctype html>
<html>
<head>
<style type="text/css">
caption {text-align: left;}
th {text-align: left;}
thead th {border-bottom: 1px solid black;}
tbody th {text-indent: 2em; padding-right: 1em;}
th.breakout {text-indent: 4em;}
</style>
</head>

<body>
<table>
  <caption>Summary processing statistics for %(tool_count)d DFXML-producing storage parsers.</caption>
  <thead>
    <tr>
      <th />
      %(html_tool_column_headers)s
    </tr>
  </thead>
  <tfoot></tfoot>
  <tbody>
    <tr><th>Partitions processed</th>%(html_row_s_parts_processed)s</tr>
    <tr><th>Allocated directories</th>%(html_row_s_allocated_dirs)s</tr>
    <tr><th>Allocated files</th>%(html_row_s_allocated_files)s</tr>
    <tr><th>Allocated other</th>%(html_row_s_allocated_other)s</tr>
    <tr><th>Unallocated directories</th>%(html_row_s_unallocated_dirs)s</tr>
    <tr><th>Unallocated files</th>%(html_row_s_unallocated_files)s</tr>
    <tr><th>Unallocated other</th>%(html_row_s_unallocated_other)s</tr>
  </tbody>
</table>
</body>
</html>""" 
            template1 = template0 % format_dict
            _logger.debug("HTML template1 = %s." % template1)
            _logger.debug("HTML stats_dict = %r." % stats_dict)
            
            formatted = template1 % stats_dict

            fh.write(formatted)

    def write_latex(self, fp):
        with open(fp, "w") as fh:
            format_dict = self._get_format_dict()
            stats_dict = self._get_stats_dict()

            #Two passes:  First, create another template string with columnar places for numeric data.  Then populate the data.
            template0 = r"""\begin{table}[htdp]
\caption{Summary processing statistics for %(tool_count)d DFXML-producing storage parsers.}
\begin{center}
\begin{tabular}{|l|%(latex_column_aligns)s|}
\hline
%(latex_tool_column_headers)s \\
\hline
Partitions processed %(latex_row_s_parts_processed)s \\
Allocated directories %(latex_row_s_allocated_dirs)s \\
Allocated files %(latex_row_s_allocated_files)s \\
Allocated other %(latex_row_s_allocated_other)s \\
Unallocated directories %(latex_row_s_unallocated_dirs)s \\
Unallocated files %(latex_row_s_unallocated_files)s \\
Unallocated other %(latex_row_s_unallocated_other)s \\
\hline
\end{tabular}
\end{center}
\label{default}
\end{table}"""
            template1 = template0 % format_dict
            
            formatted = template1 % stats_dict

            fh.write(formatted)

def main():
    global args

    tabulator = SummarizerTabulator()

    for labeled_xml_file in args.labeled_xml_file:
        parts = labeled_xml_file.split(":")
        #The 3 OR 4 is in case we're dealing with a Windows absolute path.
        if not len(parts) in [3,4]:
            raise ValueError("Argument error: The file specification must be longlabel:shortlabel:path.")
        prog = parts[0]
        xml_path = ":".join(parts[2:])
        if not os.path.exists(xml_path):
            raise ValueError("DFXML file not found: %r." % (xml_path))

        if not args.check_labeling:
            tabulator.summarize(prog, xml_path)

    if args.check_labeling:
        sys.exit(0)

    tabulator.write_latex("summary.tex")
    tabulator.write_html("summary.html")

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("labeled_xml_file", help="List of DFXML files, each colon-prefixed with a long and short label (e.g. 'Fiwalk:fi:fiout.dfxml')", nargs="+")
    argparser.add_argument("--check-labeling", help="Pre-run diagnostic: Check labeling of paths", action="store_true")
    argparser.add_argument("-d", "--debug", help="Enable debug printing", action="store_true")
    args = argparser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    main()
