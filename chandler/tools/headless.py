#   Copyright (c) 2003-2007 Open Source Applications Foundation
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


import sys, os

from types import GeneratorType
from code import interact

if '-A' in sys.argv:
    commitOnExit = False
    sys.argv.remove('-A')
else:
    commitOnExit = True

from application import schema, Utility, Globals
from chandlerdb.item.Item import Item
from chandlerdb.util.LinkedMap import LinkedMap

view = None
app = None

# This dictionary is a mapping of symbols that other modules might want
# to use; it's populated by the @exportMethod decorator below.
exportedSymbols = { }

def startup(chandlerDirectory=None, **kwds):
    global view, commitOnExit

    Globals.options = Utility.initOptions(**kwds)
    if chandlerDirectory is None:
        Globals.chandlerDirectory = Utility.locateChandlerDirectory()
    else:
        Globals.chandlerDirectory = chandlerDirectory

    os.chdir(Globals.chandlerDirectory)
    Utility.initI18n(Globals.options)

    profileDir = Globals.options.profileDir

    Utility.initLogging(Globals.options)

    parcelPath = Utility.initParcelEnv(Globals.options, 
                                       Globals.chandlerDirectory)
    pluginEnv, pluginEggs = Utility.initPluginEnv(Globals.options,
                                                  Globals.options.pluginPath)

    Globals.options.getPassword = getPassword
    repoDir = Utility.locateRepositoryDirectory(profileDir, Globals.options)
    view = Utility.initRepository(repoDir, Globals.options)

    verify, repoVersion, schemaVersion = Utility.verifySchema(view)
    if not verify:
        print "Schema mismatch (%s vs %s).  Try again with startup(create=True)" %(repoVersion, schemaVersion)
        return None

    Utility.initCrypto(Globals.options.profileDir)
    Utility.initParcels(Globals.options, view, parcelPath)
    Utility.initPlugins(Globals.options, view, pluginEnv, pluginEggs)
    Utility.initTimezone(Globals.options, view)

    if Globals.options.reload:
        from osaf import dumpreload
        dumpreload.reload(view, Globals.options.reload)

    return view


def getPassword(create=False, again=False):
    from getpass import getpass

    while True:
        if again:
            print "Invalid password"

        if create:
            password = getpass("Create password: ")
            confirmed = getpass("Confirm password: ")
        else:
            password = getpass("Enter password: ")

        if create and password != confirmed:
            print "Passwords do not match"
        else:
            return password


def exportMethod(method):
    """ Add the method to exportedSymbols """
    global exportedSymbols
    exportedSymbols[method.func_name] = method
    return method

def getExports(**kw):
    """ Return a copy of exportedSymbols, with kw included """
    exports = exportedSymbols.copy()
    exports.update(**kw)
    return exports

@exportMethod
def go(port=None):

    print "Igniting Twisted reactor..."
    if view.isNew():
        view.commit()

    if port is not None:
        Globals.options.webserver = [str(port)]
    else:
        if Globals.options.webserver is None:
            Globals.options.webserver = []

    Utility.initTwisted(view, options=Globals.options)
    Utility.initWakeup(view)
    print "...ready"

@exportMethod
def shutdown():
    Utility.stopWakeup()
    Utility.stopTwisted()
    Utility.stopRepository(view, commitOnExit)
    Utility.stopCrypto(Globals.options.profileDir)


def setDisplayHook():
    """
    Install a custom displayhook to keep Python from setting the global
    _ (underscore) to the value of the last evaluated expression.  If
    we don't do this, our mapping of _ to gettext can get overwritten.
    """
    def _displayHook(obj):
        if obj is not None:
            print repr(obj)

    sys.displayhook = _displayHook



# Repository-as-file-system commands:

currentItem = None
currentList = None

def _argToItem(arg):
    global currentItem

    if currentItem is None:
        currentItem = view

    if arg is None:
        return currentItem

    # arg is a number
    if isinstance(arg, (int, long)):
        try:
            return currentList[arg-1]
        except:
            return None

    # arg is an Item
    elif isinstance(arg, Item):
        return arg

    # arg is a string (UUID, or path either absolute or relative to currentItem)
    else:
        return view.findUUID(arg) or currentItem.findPath(arg)

@exportMethod
def getKind(kindName):
    kindKind = view.findPath("//Schema/Core/Kind")
    matching = []
    for kind in kindKind.iterItems():
        if kind.itsName == kindName:
            matching.append(kind)
    if len(matching) == 0:
        return None
    return matching[0]

@exportMethod
def ofKind(kindName, recursive=True):
    kind = getKind(kindName)
    for item in kind.iterItems(recursive=recursive):
        yield item

@exportMethod
def create(kindName):
    kind = getKind(kindName)
    return kind.newItem()

@exportMethod
def cd(arg):
    global currentItem

    item = _argToItem(arg)

    if item is not None:
        currentItem = item
        print "Current item:", item.itsPath
    else:
        print "no matching item"

@exportMethod
def pwd():
    global currentItem

    if currentItem is None:
        currentItem = view

    print currentItem.itsPath


def _getName(item):
    return (getattr(item, 'displayName', None) or item.itsName or "<unknown>")
    
@exportMethod
def ls(arg=None):
    global currentList

    if isinstance(arg, (GeneratorType, LinkedMap)):
        currentList = [item for item in arg]
    else:
        item = _argToItem(arg)
        currentList = [child for child in item.iterChildren()]

    currentList.sort(lambda x, y: cmp(_getName(x).lower(), _getName(y).lower()))

    count = 1
    for item in currentList:
        kind = item.itsKind
        if kind is None:
            kindName = "<Kindless>"
        else:
            kindName = kind.itsName
        print "%3d. %s (%s)" % (count,
                                _getName(item),
                                kindName)
        count += 1

@exportMethod
def grab(arg=None):
    return _argToItem(arg)


@exportMethod
def show(arg=None, recursive=False):
    item = _argToItem(arg)

    item.printItem(recursive)


@exportMethod
def browse(arg=None):
    item = _argToItem(arg)
    rv = item.itsView
    port = schema.ns('osaf.app', rv).mainServer.port

    import webbrowser
    path = unicode(item.itsPath)[1:]
    url = 'http://localhost:%d/repo%s' % (port, path.encode('utf8'))
    webbrowser.open(url)


@exportMethod
def readme():
    print """
This is a version of Chandler which doesn't start up the wx portion
of the code.  The repository has been opened, and packs and parcels
loaded. If you want to start Twisted services (including WakeupCallers),
you need to run the 'go( )' method from the shell.  Once you've
done that any registered web servlets will then be available at
http://localhost:1888/

This script accepts all of the command-line arguments and environment
variables as the GUI Chandler, as they share the same option-parsing
code.  Exiting the interactive session (by Control-D on *nix boxes,
and by Control-Z followed by Enter on Windows) will shut down
twisted, commit the repository, and exit the program.

Some helper methods have been defined to make it easy to move around within
the repository:  cd, pwd, ls, grab, show

- cd(item or repository path or list number)
    Either pass in an item, a path string like "//userdata", or the number of
    an item as displayed in the most recent ls() call

- pwd()
    Prints the repository path of the "current" item (the item you last
    cd'ed to)

- ls(item or repository path or list number or iterator or None)
    Lists all the child items of the argument, which is either an item,
    a repository path, a previous ls() number, an iterator, or None which
    will use the "current" item

- grab(item or repository path or list number or None)
    Returns the item corresponding to the argument, which can be an item,
    a repository path, or a previous ls() number, or None which will return
    the "current" item

- show(item or list number or repository path or None, recursive=False)
    Prints out the attributes of an item, and the argument can be an item,
    a number from the most recent ls(), a repository path, or if nothing
    is passed in it will use the "current" item.  There is an optional
    'recursive' boolean argument which defaults to False.

- browse(item or list number or repository path or None)
    Opens the web browser, rendering the item's info in the repository servlet.

- create(kind name)
    Creates and returns an item of the kind 'kind name'

- getKind(kind name)
    Returns the kind with that name

- ofKind(kind name)
    Returns an iterator of all items of that kind; nest this within an ls()
    call like:  ls( ofKind("RSSItem") )


"""

def main():
    global exportedSymbols

    print "Starting up..."

    view = startup()
    if not view:
        sys.exit(1)
    # Also add 'view' and 'app' to exportedSymbols
    exportedSymbols['view'] = view
    exportedSymbols['schema'] = schema
    exportedSymbols['app_ns'] = schema.ns('osaf.app', view)
    exportedSymbols['pim_ns'] = schema.ns('osaf.pim', view)

    setDisplayHook()

    banner = "\nWelcome!  Headless Chandler will shut down when you " \
             "exit this Python session.\n" \
             "The variable, 'view', is now set to the main repository " \
             "view, and 'app' is the\n" \
             "schema.ns('osaf.app', view) object.\n" \
             "Type 'readme()' for more info.\n"

    script = Globals.options.scriptFile
    if script:
        try:
            if Globals.options.webserver is not None:
                go()
            if script.endswith('.py'):
                file = open(script)
                script = file.read()
                file.close()

            # Lose the commandline save argv[0], because the script we're
            # invoking might not like our command line args (like unittests)
            sys.argv = sys.argv[0:1]

            exec script in globals()
        finally:
            shutdown()

    else:

        if Globals.options.webserver is not None:
            go()
        else:
            banner += "Type 'go()' to fire up Twisted services.\n"

        try:
            from IPython.Shell import IPShellEmbed
            argv = ['-pi1','In [\\#]: ','-pi2','   .\\D.:','-po','Out[\\#]: ']
            banner += """\n
In IPython-enabled headless, you have syntactic shortcuts like leaving off 
() for calls, and using '?obj' instead help(obj)."""
            exit_msg = "*** Exiting IPython ***"
            ipshell = IPShellEmbed(argv,banner=banner,exit_msg=exit_msg)
            ipshell()
        except ImportError:
            interact(banner,
                    None,
                    getExports(__name__="__console__", __doc__=None)
                    )

        print "Shutting down..."
        shutdown()


if __name__ == "__main__":
    main()
