import application.Globals as Globals

import davlib
import libxml2

import DAVItem as DAVItem

from repository.schema.Kind import Kind

def makeAndParse(xml):
    # given a chunk of text that is a flat xml tree like:
    # "<foo/><foo/><foo/>"
    # parse it and return a list of the nodes
    xmlgoop = davlib.XML_DOC_HEADER + \
              '<doc>' + \
              xml + \
              '</doc>'

    doc = libxml2.parseDoc(xmlgoop)
    nodes = doc.xpathEval('/doc/*')
    return nodes


def getItem(dav):
    from Dav import DAV
    repository = Globals.repository

    # fetch the item
    di = DAVItem.DAVItem(dav)

    # ew...
    sharing = repository.findPath('//parcels/osaf/framework/GlobalShare') 

    # pretend here we don't care if the item has changed..
    try:
        # get the exported item's UUID and see if we have already fetched it
        origUUID = di.itsUUID
        newItem = repository.findUUID(sharing.itemMap[origUUID])
        kind = newItem.itsKind
    except KeyError:
        kind = di.itsKind
        newItem = kind.newItem(None, repository.findPath('//userdata/contentitems'))

    oldEtag = newItem.getAttributeValue('etag', default=None)
    if oldEtag == di.etag:
        print 'no changes to item'
        return newItem
    else:
        print oldEtag, di.etag

    newItem.etag = di.etag
    newItem.lastModified = di.lastModified

    # XXX hack...
    sharing.itemMap[origUUID] = newItem.itsUUID

    for (name, attr) in kind.iterAttributes(True):

        value = di.getAttribute(attr)
        if not value:
            continue

        print 'Getting:', name, '(' + attr.type.itsName + ')'

        # see if its an ItemRef or not
        if isinstance(attr.type, Kind):
            # time for some xml parsing! yum!
            nodes = makeAndParse(value)

            if attr.cardinality == 'list':
                for node in nodes:
                    otherItem = DAV(node.content).get()
                    newItem.addValue(name, otherItem)
            elif attr.cardinality == 'single':
                node = nodes[0]
                otherItem = DAV(node.content).get()
                newItem.setAttributeValue(name, otherItem)
            else:
                raise Exception

        else:
            #newItem.setAttributeValue(name, value)
            print 'Got.....: ', value
            newItem.setAttributeValue(name, attr.type.makeValue(value))

    return newItem
