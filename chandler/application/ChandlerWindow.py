__author__ = "Jed Burgess"
__version__ = "$Revision$"
__date__ = "$Date$"
__copyright__ = "Copyright (c) 2003 Open Source Applications Foundation"
__license__ = "OSAF License"

from wxPython.wx import *
from wxPython.xrc import *
import application.Application
"""Ideally we'd prefer to do a "from application.Application import app", however,
because Application imports ChandlerWindow (the mutually recursive import problem),
app isn't defined yet. Further attempt postpone the include of ChandlerWindow after
app is setup lead to hairballs
"""
from Persistence import Persistent, PersistentDict


class ChandlerWindow(Persistent):
    """
      ChandlerWindow is the main window in Chandler and is the model
    counterpart wxChandlerWindow view object (see below). A ChandlerWindow
    contains all of the appropriate navigation elements along with the
    current viewer parcel.
    """
    def __init__(self):
        """
          The initial size (x, y, width, height) is set to (-1, -1, -1, -1) to
        indicate that the window should be tiled to fit the screen, rather than
        being brought up in it's last location and size.
        """
        self.size = PersistentDict.PersistentDict()
        self.size['x'] = -1
        self.size['y'] = -1
        self.size['width'] = -1
        self.size['height'] = -1        
        
    def SynchronizeView(self):
        """
          Notifies the window's wxPython view counterpart that they need to
        synchronize themselves to match their peristent model counterpart.
        """
        app = application.Application.app
        if not app.association.has_key(id(self)):
            wxWindow = app.applicationResources.LoadFrame (None, "ChandlerWindow")
            assert (wxWindow != None)
            wxWindow.SetToolBar (None)
            wxWindow.OnInit (self)
            app.association[id(self)] = wxWindow
        else:
            wxWindow = app.association[id(self)]
        
        wxWindow.MoveOntoScreen()

class wxChandlerWindow(wxFrame):

    def __init__(self):
        """
          wxChandlerWindow is the view counterpart to ChandlerWindow.
        There is a little magic incantation provided by Robin Dunn here
        to wire up the wxWindows object behind the wxPython object.
        wxPreFrame creates the wxWindows C++ object, which is stored
        in the this member. _setOORInfo store a back pointer in the C++
        object to the wxPython object.
        """
        value = wxPreFrame ()
        self.this = value.this
        self._setOORInfo (self)
        
    def OnActivate(self, event):
        """
           The Application keeps a copy of the last persistent window openn
        so that the next time we run the application we can open the same window
        """
        app = application.Application.app
        app.wxMainFrame = self
        app.model.mainFrame = self.model
        event.Skip()

    def OnInit(self, model):
        """
          There's a tricky problem here. We need to postpone wiring up OnMove,
        OnSize, etc. after __init__, otherwise OnMove, etc. will get called before
        we've had a chance to set the windows size using the value in our model.
        """
        self.model = model

        self.CreateStatusBar ()
        self.SetStatusText ("Welcome!")

        applicationResources = application.Application.app.applicationResources
        self.menuBar = applicationResources.LoadMenuBar ("MainMenuBar")
        assert (self.menuBar != None)
        self.SetMenuBar (self.menuBar)
        
        if __debug__:
            """
              In the debugging version, we add a command key combination that
            toggles a debug menu. We currently default to having it on.
            """
            toggleDebugMenuId = wxNewId()
            aTable = wxAcceleratorTable([(wxACCEL_CTRL | wxACCEL_SHIFT | wxACCEL_ALT,
                                          ord('D'), toggleDebugMenuId)])
            self.SetAcceleratorTable(aTable)
            EVT_MENU (self, toggleDebugMenuId, self.OnToggleDebugMenu)
            self.OnToggleDebugMenu (wxMenuEvent())

        EVT_MOVE(self, self.OnMove)
        EVT_SIZE(self, self.OnSize)
        EVT_CLOSE(self, self.OnClose)
        EVT_ACTIVATE(self, self.OnActivate)
        EVT_MENU(self, -1, self.OnMenuCommand)
        self.InMenuCommand = false       #used by OnMenuCommand


    if __debug__:
        def OnToggleDebugMenu(self, event):
            menuBar = self.GetMenuBar ()
            index = menuBar.FindMenu (_('Debug'))
            if index == wxNOT_FOUND:
                applicationResources = application.Application.app.applicationResources
                debugMenu = applicationResources.LoadMenu ('DebugMenu')
                menuBar.Append (debugMenu, _('Debug'))
                menuBar.Check (XRCID ('CreateNewRepository'),
                               hasattr (application.Application.app.model,
                                        'CreateNewRepository'))
            else:
                oldMenu = menuBar.Remove (index)
                del oldMenu

    def OnMove(self, event):
        """
          Calling Skip causes wxWindows to continue processing the event, which
        will cause the parent class to get a crack at the event.
        """
        event.Skip()
        self.model.size['x'] = self.GetPosition().x
        self.model.size['y'] = self.GetPosition().y

    def OnSize(self, event):
        """
          Calling Skip causes wxWindows to continue processing the event, which
        will cause the parent class to get a crack at the event.
        """
        event.Skip()
        self.model.size['width'] = self.GetSize().x
        self.model.size['height'] = self.GetSize().y

    def OnClose(self, event):
        """
          Closing the last window causes the application to quit.
        """
        del application.Application.app.association[id(self.model)]
        self.Destroy()
        
    def MoveOntoScreen(self):
        """
          Check to see if the window location is off screen and moves it onto
        screen. The code below is currently a place holder. It will change
        depending on how we handle multiple windows (e.g. tiling), multiple
        monitors and various error conditions, like changing monitor size and
        windows off the screen.
        """
        screenSize = wxClientDisplayRect ()
        """
          If the window isn't on the screen, set it to the default size and
        position.
        """
        if self.model.size['x'] < screenSize[0] or \
           self.model.size['y'] < screenSize[1] or \
           self.model.size['x'] + self.model.size['width'] > screenSize[2] or \
           self.model.size['y'] + self.model.size['height'] > screenSize[3]:
            preferences = application.Application.app.model.preferences
            self.SetSize ((preferences.windowSize['width'],
                          preferences.windowSize['height']))
            self.CentreOnScreen ()
        else:
            self.SetRect ((self.model.size['x'],
                           self.model.size['y'],
                           self.model.size['width'],
                           self.model.size['height']))
        rect = self.GetRect()
        self.model.size['x'] = rect.GetX()
        self.model.size['y'] = rect.GetY()
        self.model.size['width'] = rect.GetWidth()
        self.model.size['height'] = rect.GetHeight()
            
    def OnMenuCommand(self, event):
        """
          Catch menu commands and pass them along to the viewerParcels.
        First we let the application get a crack at the event, if it
        doesn't handle it we pass it along to the window that has the
        focus (i.e. the viewerParcel). In the event the viewerParcel doesn't
        handle the event we'll get recursively called, so we use
        InMenuCommand to ignore recursive calls.
          For some unknown reason ProcessEvent on the focusWindow always
        returns true, even when the event isn't processed, so we don't
        try the focusWindow first, followed by the application if it doesn't
        get processed.
        """
        if not self.InMenuCommand:
            self.InMenuCommand = true
            focusWindow = wxWindow_FindFocus ()
            processed = application.Application.app.ProcessEvent(event)
            if not processed:
                focusWindow.GetEventHandler().ProcessEvent(event)
            self.InMenuCommand = false
            