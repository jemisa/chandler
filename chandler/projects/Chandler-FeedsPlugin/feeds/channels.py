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


__parcel__    = "feeds"

import time, os, logging, datetime, urllib
from PyICU import ICUtzinfo, TimeZone
from dateutil.parser import parse as date_parse
from application import schema
from util import feedparser, indexes
from xml.sax import SAXParseException
from osaf import pim
from i18n import MessageFactory
from twisted.web import client
from twisted.internet import reactor
from osaf.pim.calendar.TimeZone import formatTime
from repository.util.URL import URL
from repository.util.Lob import Lob

_ = MessageFactory("Chandler-FeedsPlugin")

logger = logging.getLogger(__name__)

FETCH_UPDATED = 2
FETCH_NOCHANGE = 1
FETCH_FAILED = 0

# The Feeds repository view, used for background updates
view = None

def getFeedsView(repository):
    global view
    if view is None:
        view = repository.createView("Feeds")
    return view



class FeedUpdateTaskClass:

    def __init__(self, item):
        self.repository = item.itsView.repository
        pass

    def run(self):
        updateFeeds(self.repository)
        return True     # run it again next time


def updateFeeds(repository):
    view = getFeedsView(repository)
    view.refresh()

    for channel in FeedChannel.iterItems(view):
        channel.refresh()


def newChannelFromURL(view, url):

    url = str(url)

    channel = FeedChannel(itsView=view)
    channel.displayName = url
    channel.url = channel.getAttributeAspect('url', 'type').makeValue(url)

    return channel



# sets a given attribute overriding the name with newattr
def SetAttribute(self, data, attr, newattr=None):
    if not newattr:
        newattr = attr
    value = data.get(attr)
    if value:
        type = self.getAttributeAspect(newattr, 'type', None)
        if type is not None:
            value = type.makeValue(value)
        self.setAttributeValue(newattr, value)

def SetAttributes(self, data, attributes):
    if isinstance(attributes, dict):
        for attr, newattr in attributes.iteritems():
            SetAttribute(self, data, attr, newattr=newattr)
    elif isinstance(attributes, list):
        for attr in attributes:
            SetAttribute(self, data, attr)



class ConditionalHTTPClientFactory(client.HTTPClientFactory):

    def __init__(self, url, lastModified=None, etag=None, method='GET',
                 postdata=None, headers=None, agent="Chandler", timeout=0,
                 cookies=None, followRedirect=1):

        if lastModified or etag:
            if headers is None:
                headers = { }
            if lastModified:
                headers['if-modified-since'] = lastModified
            if etag:
                headers['if-none-match'] = etag

        client.HTTPClientFactory.__init__(self, url, method=method,
            postdata=postdata, headers=headers, agent=agent, timeout=timeout,
            cookies=cookies, followRedirect=followRedirect)

        self.deferred.addCallback(
            lambda data: (data, self.status, self.response_headers)
        )

    def noPage(self, reason):
        if self.status == '304':
            client.HTTPClientFactory.page(self, '')
        else:
            client.HTTPClientFactory.noPage(self, reason)


class FeedChannel(pim.ListCollection):

    def __init__(self, *args, **kw):
        super(FeedChannel, self).__init__(*args, **kw)
        self.addIndex('link', 'value', attribute='link')

    link = schema.One(
        schema.URL,
    )

    category = schema.One(
        schema.Text,
    )

    author = schema.One(
        schema.Text,
    )

    date = schema.One(
        schema.DateTime,
    )

    url = schema.One(
        schema.URL,
    )

    etag = schema.One(
        schema.Text,
    )

    lastModified = schema.One(
        schema.DateTime,
    )

    copyright = schema.One(
        schema.Text,
    )

    language = schema.One(
        schema.Text,
    )

    ignoreContentChanges = schema.One(
        schema.Boolean,
        initialValue=False
    )
    
    isEstablished = schema.One(
        schema.Boolean,
        initialValue=False
    )

    isPreviousUpdateSuccessful = schema.One(
        schema.Boolean,
        initialValue=True
    )
    
    logItem = schema.One(
        initialValue=None
    )

    schema.addClouds(
        sharing = schema.Cloud(author, copyright, link, url)
    )

    who = schema.Descriptor(redirectTo="author")


    def refresh(self, callback=None):

        # Make sure we have the feedsView copy of the channel item
        feedsView = getFeedsView(self.itsView.repository)
        feedsView.refresh()
        item = feedsView.findUUID(self.itsUUID)
        
        return item.download().addCallback(item.feedFetchSuccess, callback).addErrback(
            item.feedFetchFailed, callback)


    def download(self):
        url = str(self.url)
        etag = str(getattr(self, 'etag', None))
        lastModified = getattr(self, 'lastModified', None)
        if lastModified:
            lastModified = lastModified.strftime("%a, %d %b %Y %H:%M:%S %Z")

        (scheme, host, port, path) = client._parse(url)
        scheme = str(scheme)
        host = str(host)
        path = str(path)
        factory = ConditionalHTTPClientFactory(url=url,
            lastModified=lastModified, etag=etag)
        reactor.connectTCP(host, port, factory)

        return factory.deferred



    def feedFetchSuccess(self, info, callback=None):

        (data, status, headers) = info

        # getattr returns a unicode object which needs to be converted to
        # bytes for logging
        channel = getattr(self, 'displayName', None)
        if channel is None:
            channel = str(self.url)
        else:
            channel = channel.encode('ascii', 'replace')

        if not data:
            # Page hasn't changed (304)
            logger.info("Channel hasn't changed: %s" % channel)
            return FETCH_NOCHANGE

        logger.info("Channel downloaded: %s" % channel)

        # set etag
        etag = headers.get('etag', None)
        if etag:
            self.etag = etag[0]

        # set lastModified
        lastModified = headers.get('last-modified', None)
        if lastModified:
            self.lastModified = date_parse(lastModified[0])

        count = self.parse(data)
        if count:
            logger.info("...added %d FeedItems" % count)
            
        self.isEstablished = True
        self.isPreviousUpdateSuccessful = True
        self.logItem = None
        
        self.itsView.commit()
        
        if callback:
            callback(self.itsUUID, True)
            
        return FETCH_UPDATED


    def feedFetchFailed(self, failure, callback=None):

        # getattr returns a unicode object which needs to be converted to
        # bytes for logging
        channel = getattr(self, 'displayName', None)
        if channel is None:
            channel = str(self.url)
        else:
            channel = channel.encode('ascii', 'replace')

        logger.error("Failed to update channel: %s; Reason: %s",
            channel, failure.getErrorMessage())

        if self.isEstablished:
            if self.isPreviousUpdateSuccessful:
                self.isPreviousUpdateSuccessful = False
                item = FeedItem(itsView=self.itsView)
                item.displayName = _(u"Feed channel is unreachable")
                item.author = _(u"Chandler Feeds Parcel")
                item.category = _(u"Internal")
                item.date = datetime.datetime.now(ICUtzinfo.default)
                item.content = view.createLob(_(u"This feed channel is currently unreachable"))
                self.addFeedItem(item)
                self.logItem = item
                self.itsView.commit()
            else:
                if self.logItem:
                    self.logItem.content = view.createLob(u"This feed channel has been unreachable from " + unicode(formatTime(self.logItem.date)) + u" to " + unicode(formatTime(datetime.datetime.now(ICUtzinfo.default))))
                    self.itsView.commit()

        if callback:
            callback(self.itsUUID, False)
            
        return FETCH_FAILED


    def parse(self, rawData):

        data = feedparser.parse(rawData)

        # For fun, keep the latest copy of the feed inside the channel item
        self.body = unicode(rawData, 'utf-8')

        return self.fillAttributes(data)


    def fillAttributes(self, data):
        # Map some external attribute names to internal attribute names:
        attrs = {'title':'displayName', 'description':'body'}
        SetAttributes(self, data['channel'], attrs)

        # These attribute names don't need remapping:
        attrs = ['link', 'copyright', 'category', 'language']
        SetAttributes(self, data['channel'], attrs)

        date = data['channel'].get('date')
        if date:
            self.date = date_parse(str(date))

        return self._parseItems(data['items'])


    def addFeedItem(self, feedItem):
        """
            Add a single item, and add it to any listening collections
        """
        feedItem.channel = self
        self.add(feedItem)


    def _parseItems(self, items):

        view = self.itsView

        count = 0

        for newItem in items:

            # Convert date to datetime object
            if getattr(newItem, 'date_parsed', None):

                try:

                    # date_parsed is a tuple of 9 integers, like gmtime( )
                    # returns...
                    d = newItem.date_parsed

                    # date_parsed seems to always be converted to GMT, so
                    # let's make a datetime object using values from
                    # date_parsed, coupled with a GMT tzinfo...
                    itemDate = datetime.datetime(d[0], d[1], d[2], d[3], d[4],
                        d[5], 0, ICUtzinfo(TimeZone.getGMT()))

                    # logger.debug("%s, %s, %s" % \
                    #     (newItem.date, newItem.date_parsed, itemDate))

                    newItem.date = itemDate

                except:
                    logger.exception("Couldn't get date: %s (%s)" % \
                        (newItem.date, newItem.date_parsed))
                    newItem.date = None


            # Get the item content, using the 'content' attribute first,
            # falling back to what's in'description'
            content = newItem.get('content')
            if content:
                content = content[0]['value']
            else:
                content = newItem.get('description')

            title = newItem.get('title')

            matchingItem = None
            link = getattr(newItem, 'link', None)
            if link:
                # Find all FeedItems that have this link
                matchingItem = indexes.valueLookup(self, 'link', 'link', link)

            # If no matching items (based on link), it's new
            # If matching item, if title or description have changed,
            # update the item and mark it unread

            if matchingItem is None:

                feedItem = FeedItem(itsView=view)
                feedItem.refresh(newItem)
                self.addFeedItem(feedItem)
                logger.debug("Added new item: %s", title)
                count += 1

            else:
                # A FeedItem exists within this Channel that has the
                # same link.  @@@MOR For now I am only going to allow one
                # FeedItem at a time (per Channel) to link to the same place,
                # since it seems like that gets the behavior we want.

                oldTitle = matchingItem.displayName
                titleDifferent = (oldTitle != title)

                # If no date in the item, just consider it a matching date;
                # otherwise do compare datestamps:
                dateDifferent = False
                haveFeedDate = 'date' in newItem
                if haveFeedDate:
                    if matchingItem.date != newItem.date:
                        dateDifferent = True

                if not self.ignoreContentChanges:
                    oldContent = matchingItem.content.getReader().read()
                    contentDifferent = (oldContent != content)
                else:
                    contentDifferent = False

                if contentDifferent or titleDifferent or dateDifferent:

                    matchingItem.refresh(newItem)

                    if matchingItem.read:
                        matchingItem.updated = True

                    matchingItem.read = False

                    msg = "Updated item: %s (content %s, title %s, date %s)"
                    logger.debug(msg, title, contentDifferent, titleDifferent,
                                 dateDifferent)

        return count

    def markAllItemsRead(self):
        for item in self:
            item.read = True

##
# FeedItem
##
class FeedItem(pim.ContentItem):

    link = schema.One(
        schema.URL,
        initialValue=None
        #initialValue=URL(u""), # Needed because of the _compareLink( ) method
    )

    category = schema.One(
        schema.Text,
    )

    author = schema.One(
        schema.Text,
    )

    date = schema.One(
        schema.DateTime,
    )

    channel = schema.One(
        FeedChannel,
    )

    content = schema.One(
        schema.Lob,
    )

    updated = schema.One(
        schema.Boolean,
    )

    about = schema.Descriptor(redirectTo="displayName")
    who = schema.Descriptor(redirectTo="author")
    body = schema.Descriptor(redirectTo="content")

    schema.addClouds(
        sharing = schema.Cloud(link, category, author, date)
    )

    def __init__(self, *args, **kw):
        kw.setdefault('displayName', _(u"No Title"))
        super(FeedItem, self).__init__(*args, **kw)

    def _compareLink(self, other):
        return cmp(str(self.link).lower(), str(other.link).lower())

    def refresh(self, data):
        # fill in the item
        attrs = {'title':'displayName'}
        SetAttributes(self, data, attrs)

        attrs = ['link', 'category', 'author']
        # @@@MOR attrs = ['creator', 'link', 'category']
        SetAttributes(self, data, attrs)

        content = data.get('content')

        # Use the 'content' info first, falling back to what's in 'description'
        if content:
            content = content[0]['value']
        else:
            content = data.get('description')

        if content:
            self.content = self.getAttributeAspect('content', 'type').makeValue(content, indexed=True)

        if 'date' in data:
            self.date = date_parse(str(data.date))
        else:
            # No date was available in the feed, so assign it 'now'
            self.date = datetime.datetime.now(ICUtzinfo.default)
