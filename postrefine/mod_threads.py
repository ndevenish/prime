from __future__ import division

"""
Author      : Lyubimov, A.Y.
Created     : 05/01/2016
Last Changed: 08/23/2016
Description : PRIME GUI Threading module
"""

import os
import wx
from threading import Thread

from libtbx import easy_run
import iota.components.iota_controls as ct

# Platform-specific stuff
# TODO: Will need to test this on Windows at some point
if wx.Platform == "__WXGTK__":
    norm_font_size = 10
    button_font_size = 12
    LABEL_SIZE = 14
    CAPTION_SIZE = 12
    python = "python"
elif wx.Platform == "__WXMAC__":
    norm_font_size = 12
    button_font_size = 14
    LABEL_SIZE = 14
    CAPTION_SIZE = 12
    python = "Python"
elif wx.Platform == "__WXMSW__":
    norm_font_size = 9
    button_font_size = 11
    LABEL_SIZE = 11
    CAPTION_SIZE = 9

user = os.getlogin()
icons = os.path.join(os.path.dirname(os.path.abspath(ct.__file__)), "icons/")


def str_split(string, delimiters=(" ", ","), maxsplit=0):
    import re

    rexp = "|".join(map(re.escape, delimiters))
    return re.split(rexp, string, maxsplit)


# -------------------------------- Threading --------------------------------- #

# Set up events for finishing one cycle and for finishing all cycles
tp_EVT_ALLDONE = wx.NewEventType()
EVT_ALLDONE = wx.PyEventBinder(tp_EVT_ALLDONE, 1)


class AllDone(wx.PyCommandEvent):
    """Send event when finished all cycles."""

    def __init__(self, etype, eid):
        wx.PyCommandEvent.__init__(self, etype, eid)


class PRIMEThread(Thread):
    """Worker thread; generated so that the GUI does not lock up when
    processing is running."""

    def __init__(self, parent, prime_file, out_file, command=None):
        Thread.__init__(self)
        self.parent = parent
        self.prime_file = prime_file
        self.out_file = out_file
        self.command = command

    def run(self):
        if os.path.isfile(self.out_file):
            os.remove(self.out_file)
        if self.command is None:
            cmd = "prime.run {}".format(self.prime_file, self.out_file)
        else:
            cmd = self.command

        easy_run.fully_buffered(cmd, join_stdout_stderr=True)
