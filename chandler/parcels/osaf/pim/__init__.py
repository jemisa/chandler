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


# Import classes whose schemas are part of this parcel
# (this should include all ContentItem subclasses in this package)
#
from calculated import Calculated
from items import (
    ContentKind, ContentItem, ImportanceEnum, Group, Principal, 
    Project, Tag, TriageEnum, getTriageStatusName,
    getNextTriageStatus, UserNotification
)
from notes import Note
from contacts import Contact, ContactName
from calendar.Calendar import CalendarEvent, CalendarEventMixin, LONG_TIME, \
                              zero_delta
from calendar.Calendar import Calendar, Location, RecurrencePattern
from calendar.TimeZone import installParcel as tzInstallParcel
from calendar.DateTimeUtil import (ampmNames, durationFormat, mediumDateFormat, 
     monthNames, sampleDate, sampleTime, shortDateFormat, shortTimeFormat, 
     weekdayNames, weekdayName)
from reminders import Remindable, Reminder
from tasks import Task, TaskMixin
from mail import EmailAddress
from application.Parcel import Reference
from collections import KindCollection, ContentCollection, \
     DifferenceCollection, UnionCollection, IntersectionCollection, \
     FilteredCollection, ListCollection, SmartCollection, AppCollection, \
     IndexedSelectionCollection
from repository.item.Item import Item
from PyICU import ICUtzinfo

import tasks, mail, calendar.Calendar
from i18n import ChandlerMessageFactory as _


# Stamped Kinds

from application import schema

class MailedTask(tasks.TaskMixin, mail.MailMessage):
    schema.kindInfo(
        description = "A Task stamped as a Mail, or vica versa",
    )

class MailedEvent(calendar.Calendar.CalendarEventMixin, mail.MailMessage):
    schema.kindInfo(
        description = "An Event stamped as a Mail, or vica versa",
    )

class EventTask(
    tasks.TaskMixin,
    tasks.TaskEventExtraMixin,
    calendar.Calendar.CalendarEvent
):
    schema.kindInfo(
        description = "A Task stamped as an Event, or vica versa",
    )

class MailedEventTask(
    tasks.TaskMixin,
    tasks.TaskEventExtraMixin,
    calendar.Calendar.CalendarEventMixin,
    mail.MailMessage
):
    schema.kindInfo(
        description = "A Task stamped as an Event stamped as Mail, in any sequence",
    )


class NonRecurringFilter(Item):

    def isNonRecurring(self, view, uuid):

        isGenerated, modificationFor = view.findValues(uuid, ('isGenerated', False), ('modificationFor', None))

        return not (isGenerated or modificationFor)

class LongEventFilter(Item):

    def isLongEvent(self, view, uuid):
        return view.findValue(uuid, 'duration', zero_delta) > LONG_TIME

class FloatingEventFilter(Item):

    def isFloatingEvent(self, view, uuid):
        anyTime, allDay, start = view.findValues(uuid, ('anyTime',   False),
                                                       ('allDay',    False),
                                                       ('startTime', None))
        return (anyTime or allDay or (start is not None and
                                     start.tzinfo == ICUtzinfo.floating))


UTC = ICUtzinfo.getInstance("UTC")

class UTCEventFilter(Item):

    def isUTCEvent(self, view, uuid):
        anyTime, allDay, start = view.findValues(uuid, ('anyTime',   False),
                                                       ('allDay',    False),
                                                       ('startTime', None))
        if anyTime or allDay:
            return False
        return (start is not None and start.tzinfo == UTC)
    

def installParcel(parcel, oldVersion=None):
    view = parcel.itsView


    Reference.update(parcel, 'currentContact')
    Reference.update(parcel, 'currentMailAccount')
    Reference.update(parcel, 'currentSMTPAccount')

    trashCollection = ListCollection.update(
        parcel, 'trashCollection',
        displayName=_(u"Trash"))

    notes = KindCollection.update(
        parcel, 'notes',
        kind = Note.getKind(view),
        recursive = True)

    mine = UnionCollection.update(parcel, 'mine')

    # it would be nice to get rid of these intermediate fully-fledged
    # item collections, and replace them with lower level Set objects
    mineNotes = IntersectionCollection.update(parcel, 'mineNotes',
                                              sources=[mine, notes])

    nonRecurringNotes = FilteredCollection.update(parcel, 'nonRecurringNotes',
        source=mineNotes,
        filterMethod=(NonRecurringFilter(None, parcel), 'isNonRecurring'),
        filterAttributes=['isGenerated', 'modificationFor']
    )

    itemKindCollection = KindCollection.update(
        parcel, 'items',
        kind = ContentItem.getKind(view),
       recursive=True)

    itemsWithRemindersIncludingTrash = FilteredCollection.update(
        parcel, 'itemsWithRemindersIncludingTrash',
        source=itemKindCollection,
        filterExpression="view.hasTrueValue(uuid, 'reminders')",
        filterAttributes=['reminders'])

    itemsWithReminders = AppCollection.update(
        parcel, 'itemsWithReminders',
        source=itemsWithRemindersIncludingTrash,
        exclusions=trashCollection,
        trash=None,
    )

    # the monitor list assumes all reminders will be relativeTo
    # effectiveStartTime, which is true in 0.6, but may not be in the future
    itemsWithReminders.addIndex('reminderTime', 'compare',
                                compare='cmpReminderTime',
                                monitor=('startTime', 'allDay', 'anyTime'
                                         'reminders'))

    # the "All" / "My" collection
    allCollection = SmartCollection.update(parcel, 'allCollection',
        displayName=_(u"Dashboard"),
        source=nonRecurringNotes,
        exclusions=trashCollection,
        trash=None,
    )
    # kludge to improve on bug 4144 (not a good long term fix but fine for 0.6)
    allCollection.addIndex('__adhoc__', 'numeric')


    events = KindCollection.update(parcel, 'events',
        kind = CalendarEventMixin.getKind(view),
        recursive = True)
    events.addIndex("effectiveStart", 'compare', compare='cmpStartTime',
                    monitor=('startTime', 'allDay', 'anyTime'))
    events.addIndex('effectiveEnd', 'compare', compare='cmpEndTime',
                    monitor=('startTime', 'allDay', 'anyTime', 'duration'))
    events.addIndex("effectiveStartNoTZ", 'compare', compare='cmpStartTimeNoTZ',
                    monitor=('startTime', 'allDay', 'anyTime'))
    events.addIndex('effectiveEndNoTZ', 'compare', compare='cmpEndTimeNoTZ',
                    monitor=('startTime', 'allDay', 'anyTime', 'duration'))
    
    events.addIndex('icalUID', 'value', attribute='icalUID')
    
    # floatingEvents need to be reindexed in effectiveStart and effectiveEnd
    # when the floating timezone changes
    floatingEvents = FilteredCollection.update(parcel, 'floatingEvents',
        source = events,
        filterMethod= (FloatingEventFilter(None, parcel), 'isFloatingEvent'),
        filterAttributes = ['anyTime', 'allDay', 'startTime'])
    floatingEvents.addIndex('__adhoc__', 'numeric')

    # UTCEvents need to be reindexed in effectiveStartNoTZ and effectiveEndNoTZ
    # when the floating timezone changes, because UTC events are treated
    # specially
    UTCEvents = FilteredCollection.update(parcel, 'UTCEvents',
        source = events,
        filterMethod= (UTCEventFilter(None, parcel), 'isUTCEvent'),
        filterAttributes = ['anyTime', 'allDay', 'startTime'])
    UTCEvents.addIndex('__adhoc__', 'numeric')

    longEvents = FilteredCollection.update(parcel, 'longEvents',
        source = events,
        filterMethod= (LongEventFilter(None, parcel), 'isLongEvent'),
        filterAttributes = ['duration'])
    longEvents.addIndex('effectiveStart', 'subindex',
                        superindex=(events, events.__collection__,
                                    'effectiveStart'))
    longEvents.addIndex('effectiveStartNoTZ', 'subindex',
                        superindex=(events, events.__collection__,
                                    'effectiveStartNoTZ'))
    longEvents.addIndex('effectiveEnd', 'subindex',
                        superindex=(events, events.__collection__,
                                    'effectiveEnd'))
    longEvents.addIndex('effectiveEndNoTZ', 'subindex',
                        superindex=(events, events.__collection__,
                                    'effectiveEndNoTZ'))
    
    masterFilter = "view.hasTrueValues(uuid, 'occurrences', 'rruleset')"
    masterEvents = FilteredCollection.update(parcel, 'masterEvents',
        source = events,
        filterExpression = masterFilter,
        filterAttributes = ['occurrences', 'rruleset'])

    masterEvents.addIndex("recurrenceEnd", 'compare', compare='cmpRecurEnd',
                          monitor=('recurrenceEnd'))

    masterEvents.addIndex("recurrenceEndNoTZ", 'compare', compare='cmpRecurEndNoTZ',
                          monitor=('recurrenceEnd'))

    masterEvents.addIndex('effectiveStart', 'subindex',
                          superindex=(events, events.__collection__,
                                      'effectiveStart'))
    masterEvents.addIndex('effectiveStartNoTZ', 'subindex',
                          superindex=(events, events.__collection__,
                                      'effectiveStartNoTZ'))

    locations = KindCollection.update(
        parcel, 'locations',
        kind = Location.getKind(view),
        recursive = True)

    locations.addIndex('locationName', 'attribute', attribute = 'displayName')

    mailCollection = KindCollection.update(
        parcel, 'mailCollection',
        kind = mail.MailMessageMixin.getKind(view),
        recursive = True)

    emailAddressCollection = \
        KindCollection.update(parcel, 'emailAddressCollection',
                              kind=mail.EmailAddress.getKind(view),
                              recursive=True)
    emailAddressCollection.addIndex('emailAddress', 'compare',
                                    compare='_compareAddr', 
                                    monitor='emailAddress')
    emailAddressCollection.addIndex('fullName', 'compare',
                                    compare='_compareFullName', 
                                    monitor='fullName')

    inSource = FilteredCollection.update(
        parcel, 'inSource',
        source=mailCollection,
        filterExpression=u"not view.findValue(uuid, 'isOutbound', True)",
        filterAttributes=['isOutbound'])

    # The "In" collection
    inCollection = SmartCollection.update(parcel, 'inCollection',
        displayName=_(u"In"),
        source=inSource,
        trash=trashCollection,
        visible=False)

    mine.addSource(inCollection)

    outSource = FilteredCollection.update(parcel, 'outSource',
        source=mailCollection,
        filterExpression=u"view.findValue(uuid, 'isOutbound', False)",
        filterAttributes=['isOutbound'])

    # The "Out" collection
    outCollection = SmartCollection.update(parcel, 'outCollection',
        displayName=_(u"Out"),
        visible=False,
        source=outSource,
        trash=trashCollection,
    )

    mine.addSource(outCollection)

    allEventsCollection = IntersectionCollection.update(parcel,
        'allEventsCollection',
         sources=[allCollection, events]
    )

    KindCollection.update(parcel, 'notificationCollection',
        displayName=_(u"Notifications"),
        kind=UserNotification.getKind(view),
        recursive=True).addIndex('timestamp', 'value', attribute='timestamp')
        
    tzInstallParcel(parcel)

del schema  # don't leave this lying where others might accidentally import it

