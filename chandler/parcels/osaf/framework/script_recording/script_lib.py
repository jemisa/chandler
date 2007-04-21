#   Copyright (c) 2003-2006 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import wx
from osaf.framework.blocks.Block import Block
from application.Application import stringToId
from osaf.framework.attributeEditors.AETypeOverTextCtrl import AETypeOverTextCtrl

def ProcessEvent (theClass, properties , attributes):
    def NameToWidget (name):
        """
        Given a name, returns the corresponding widget.
        """
        sentTo = None
        if type (name) is str:
            if name == "MainFrame":
                sentTo = application.mainFrame
            elif name == "__FocusWindow__":
                sentTo = wx.Window_FindFocus()
            else:
                sentTo = Block.findBlockByName (name)
                if sentTo is not None:
                    sentTo = sentTo.widget
                    if isinstance (sentTo, wx.grid.Grid):
                        sentTo = sentTo.GetGridWindow()
                    elif isinstance (sentTo, AETypeOverTextCtrl):
                          firstChild = sentTo.GetChildren()[0]
                          if isinstance (firstChild, wx.TextCtrl):
                              sentTo = firstChild
                else:
                    name = stringToId [name]
        if sentTo is None:
            sentTo = wx.FindWindowById (name)
        return sentTo

    application = wx.GetApp()
    event = theClass()
    
    for (attribute, value) in attributes.iteritems():
        setattr (event, attribute, value)
    
    sentToWidget = NameToWidget (properties ["sentTo"])
    
    assert isinstance (sentToWidget, wx.Window) or isinstance (sentToWidget, wx.Menu)
    event.SetEventObject (sentToWidget)
    eventType = properties["eventType"]
    event.SetEventType (eventType.evtType[0])

    # Use the associated window if present to set the Id of the event
    associatedBlock = properties.get ("associatedBlock", None)
    if associatedBlock is not None:
        event.SetId (Block.findBlockByName (associatedBlock).widget.GetId())

    newFocusWindow = properties.get ("newFocusWindow", None)
    if newFocusWindow != None:
        ProcessEvent.newFocusWindow = newFocusWindow
        ProcessEvent.newFocusWindowClass = properties["newFocusWindowClass"]
            
    # Special case clicks on checkboxes to toggle the widget's value
    # And special case wx,Choice to set the selection. Both of these
    # are necessary before the event is processed so the GetValue
    # validation passes
    if eventType is wx.EVT_CHECKBOX:
        sentToWidget.SetValue (not sentToWidget.GetValue())

    # andSpecial case wx,Choice to set the selection
    elif eventType is wx.EVT_CHOICE:
        sentToWidget.SetSelection (properties ["selectedItem"])

    # A bug in wxWidgets on Windows stores the wrong value for m_rawCode in wx.EVT_CHAR
    # Since the correct valus is stored in wx.EVT_KEY_DOWN and wx.EVT_KEY_DOWN
    # precedes wx.EVT_KEY_DOWN, we'll cache it for the next wx.EVT_KEY_DOWN
    # Raw key codes are only used on Windows. There they correspond to virtual
    # keycodes. For this reason we record scripts on Windows to play back on the
    # other platforms.
    if eventType is wx.EVT_KEY_DOWN:
        ProcessEvent.last_rawCode = event.m_rawCode

    # Do validations
    if ProcessEvent.verifyOn:
        # Make sure the menu or button is enabled
        if eventType is wx.EVT_MENU:
            updateUIEvent = wx.UpdateUIEvent (event.GetId())
            updateUIEvent.SetEventObject (sentToWidget)
            sentToWidget.ProcessEvent (updateUIEvent)
            assert updateUIEvent.GetEnabled() is True, "You're sending a command to a disable menu"
            
        # Check to makee sure we're focused to the right window
        newFocusWindow = ProcessEvent.newFocusWindow
        if newFocusWindow is not None:
            focusWindow = wx.Window_FindFocus()
            
            # On Macintosh there is a setting under SystemPreferences>Keyboar&Mouse>KeyboardShortcuts
            # neare the bottom of the page titled "Full Keyboard Access" that defaults to
            # not letting you set the focus to certain controls, e.g. CheckBoxes. So we
            # don't verify the focus in those cases.
            if ('__WXMAC__' not in wx.PlatformInfo or
                not issubclass (ProcessEvent.newFocusWindowClass, wx.CheckBox)):

                if type (newFocusWindow) is str:
                    assert focusWindow is NameToWidget (newFocusWindow), "An unexpected window has the focus"
                else:
                    assert isinstance (focusWindow, ProcessEvent.newFocusWindowClass), "The focus window, " + str(focusWindow) + ", is not class " + str (theClass) + ". Parent window is " + str (focusWindow.GetParent())
                    if newFocusWindow > 0:
                        assert focusWindow.GetId() == newFocusWindow, "Focus window has unexpected id"
                    else:
                        assert focusWindow.GetId() < 0, "Focus window has unexpected id"
    
        # Check to make sure last event caused expected change
        if ProcessEvent.lastSentToWidget is not None:
            method = getattr (ProcessEvent.lastSentToWidget, "GetValue", None)
            lastWidgetValue = properties.get ("lastWidgetValue", None)
            if lastWidgetValue is not None and method is not None:
                value = method()
                # Special hackery for string that varies depending on Chandler build
                if type (value) is unicode and value.startswith (u"Welcome to Chandler 0.7.dev-r"):
                    assert lastWidgetValue.startswith (u"Welcome to Chandler 0.7.dev-r")
                else:
                     assert value == lastWidgetValue, "widget's value doesn't match the value when the script was recorded"
            else:
                assert lastWidgetValue is None, "last widget differes from its value when the script was recorded"

    if not sentToWidget.ProcessEvent (event):
        if (eventType is wx.EVT_KEY_DOWN and
            event.m_keyCode in set ((wx.WXK_ESCAPE, wx.WXK_TAB, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER))):
            # Special case key downs that end edits in the grid
            gridWindow = sentToWidget.GetParent()
            if (gridWindow is not None and
                isinstance (gridWindow.GetParent(), wx.grid.Grid)):
                event.SetEventObject (gridWindow)
                gridWindow.ProcessEvent (event)

        elif eventType is wx.EVT_CHAR:
            # Try EmulateKeyPress
            EmulateKeyPress = getattr(sentToWidget, 'EmulateKeyPress', None)
            if EmulateKeyPress is not None:
                # A bug in wxWidgets on Windows stores the wrong value for m_rawCode in wx.EVT_CHAR
                # Since the correct valus is stored in wx.EVT_KEY_DOWN and wx.EVT_KEY_DOWN
                # precedes wx.EVT_KEY_DOWN, we'll cache it for the next wx.EVT_KEY_DOWN
                event.m_rawCode = ProcessEvent.last_rawCode
                EmulateKeyPress (event)

        # Left down changes the focus
        elif eventType is wx.EVT_LEFT_DOWN:
            sentToWidget.SetFocus()

    selectionRange = properties.get ("selectionRange", None)
    if selectionRange is not None:
        (start, end) = selectionRange
        sentToWidget.SetSelection (start, end)

    ProcessEvent.lastSentToWidget = sentToWidget
    
    # On windows when we propagate notifications while editing a text control
    # it will end up calling wxSynchronizeWidget in wxTable, which will end the
    # editing of the table
    if not isinstance (sentToWidget, wx.TextCtrl):
        application.propagateAsynchronousNotifications()

    application.Yield()
    
    # Since scrips don't actually move the cursor and cause wxMouseCaptureLostEvents
    # to be generated we'll periodically release the capture from all the windows.
    # Alternatively, it might be better to record and playback wxMouseCaptureLostEvents.
    while True:
        capturedWindow = wx.Window.GetCapture()
        if capturedWindow is not None:
            capturedWindow.ReleaseMouse()
        else:
            break

def VerifyOn (verify = True):
    ProcessEvent.verifyOn = verify
    ProcessEvent.lastSentToWidget = None
    ProcessEvent.newFocusWindow = None

