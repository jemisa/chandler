__version__ = "$Revision$"
__date__ = "$Date$"
__copyright__ = "Copyright (c) 2002 Open Source Applications Foundation"
__license__ = "http://osafoundation.org/Chandler_0.1_license_terms.htm"

from repository.item.Item import Item
from repository.parcel.Parcel import Parcel
from repository.schema.AutoKind import AutoKind
from repository.util.ThreadLocal import ThreadLocal
from repository.util.UUID import UUID

repository=None

class AutoItem (Item, AutoKind):
    def __init__(self, name = None, parent = None, kind = None):
        if not kind:
            kind = self.GetKind ()
        if not parent:
            parent = self.__class__.threadLocal.itemBag
        super (AutoItem, self).__init__ (name, parent, kind)

    def SetRepository (theClass, theRepository):
        """
          We need to set the repository only once.
        """
        global repository
        assert not repository
        repository = theRepository
    SetRepository = classmethod (SetRepository)

    def GetKind (theClass):
        """
          The class method that is used to lookup the repository kind
        or create one if it doesn't exist.
          Store references to Items in thread local storage.
        """
        assert repository  #remember to call SetRepository before using AutoItem
        if not hasattr (theClass, 'threaded'):
            theClass.threadLocal = ThreadLocal()

        try:
            kind = theClass.threadLocal.kind
        except AttributeError:
            firstBaseClass = theClass.__bases__[0]
            if firstBaseClass is Item:
                superKind = None
                kindKind = repository.find('//Schema/Core/Kind')
            else:
                superKind = firstBaseClass.GetKind ()
                kindKind = superKind.kind
            """
              Find the parent and while we're at it, make sure
            the path contains containers.
            """
            modulePath = theClass.__module__.replace ('.', '/')
            parent = repository.walk ('//Schema/parcels/' + modulePath,
                                      lambda parent, childName, child, **kwds:
                                      child or Parcel(childName, parent, None))
            theClass.threadLocal.itemBag = \
                repository.walk ('//parcels/' + modulePath,
                                 lambda parent, childName, child, **kwds:
                                 child or Parcel(childName, parent, None))

            name = theClass.__name__
            kind = parent.getItemChild(name)
            if not kind:
                kind = kindKind.newItem (name, parent)
                if superKind:
                    kind.setValue('superKinds', superKind)
                kind.setValue('classes', theClass, 'python')

            theClass.threadLocal.kind = kind
        return kind
    GetKind = classmethod (GetKind)

    def newAttribute (self, name, theValue, theOtherName=None):
        """
          Adds an attribute name value pair. Items are added as a reference with
          an attribute name and a default otherName.
          
          Make sure name is not in use
        """
        assert not hasattr (self, name)
        assert not self.hasAttributeValue (name)

        if isinstance (theValue, Item):
            if not theOtherName:
                theOtherName = type(self).__name__

            assert not hasattr (theValue, theOtherName)
            assert not theValue.hasAttributeValue (theOtherName)

            self.createAttribute (name,
                                  value = theValue,
                                  otherName = theOtherName,
                                  deletePolicy = 'cascade',
                                  countPolicy = 'count')
            
        else:
            self.createAttribute (name, value = theValue )

    def newReferenceCollection (self, name, theOtherName=None, **args):
        """
          Create a reference collection
        """
        assert not hasattr (self, name)
        assert not self.hasAttributeValue (name)
        if not theOtherName:
            theOtherName = type(self).__name__
        self.createAttribute (name, cardinality='list', values=[], otherName=theOtherName, **args)

    def addItemToReferenceCollection (self, collection, theValue, theOtherName=None):
        if not theOtherName:
            theOtherName = type(self).__name__

        assert not hasattr (theValue, theOtherName)
        assert not theValue.hasAttributeValue (theOtherName)

        theValue.createAttribute (theOtherName,
                                  otherName=str (collection),
                                  deletePolicy = 'cascade',
                                  countPolicy = 'count')

        self.setValue(collection, value = theValue)
