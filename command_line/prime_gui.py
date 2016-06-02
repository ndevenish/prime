from __future__ import division

# LIBTBX_SET_DISPATCHER_NAME prime
# LIBTBX_PRE_DISPATCHER_INCLUDE_SH export PHENIX_GUI_ENVIRONMENT=1
# LIBTBX_PRE_DISPATCHER_INCLUDE_SH export BOOST_ADAPTBX_FPE_DEFAULT=1

"""
Author      : Lyubimov, A.Y.
Created     : 05/19/2016
Last Changed: 06/01/2016
Description : PRIME GUI startup module.
"""

import wx
import numpy as np
from prime.postrefine.mod_gui_init import PRIMEWindow


class MainApp(wx.App):
    """App for the main GUI window."""

    def OnInit(self):
        self.frame = PRIMEWindow(None, -1, title="PRIME")
        self.frame.SetPosition((150, 150))
        self.frame.SetMinSize(self.frame.GetEffectiveMinSize())
        self.frame.Show(True)
        self.SetTopWindow(self.frame)
        return True

    def workaround(self):
        """An idiotic workaround to avoid a Boost Python crash that happens
        when any PRIME module is imported; numpy has to be imported prior to
        any PRIME module; this function calls numpy to avoid the "unused
        import" error.

        Someday we will fix this.
        """
        wrk = np.mean(range(100))


if __name__ == "__main__":
    app = MainApp(0)
    app.MainLoop()
