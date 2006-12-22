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

from detailblocks import (
    installParcel,
    makeArea,
    makeEditor,
    makeLabel,
    makeSpacer,
    makeSubtree,
    uniqueName
)

from detail import (
    BylineAEBlock,
    CalendarAllDayAreaBlock,
    EventAreaBlock,
    CalendarConditionalLabelBlock,
    CalendarLocationAreaBlock, 
    CalendarRecurrenceCustomAreaBlock, 
    CalendarRecurrenceEndAreaBlock, 
    CalendarRecurrencePopupAreaBlock, 
    CalendarRecurrenceSpacer2Area, 
    CalendarStampButtonBlock,
    CalendarTimeAEBlock,
    CalendarTimeZoneAreaBlock,
    DetailRootBlock, 
    DetailSynchronizedAttributeEditorBlock,
    DetailSynchronizedContentItemDetail,
    DetailSynchronizer,
    DetailBranchPointDelegate, 
    EmptyPanelBlock,
    HTMLDetailArea,
    InboundOnlyAreaBlock,
    MailAreaBlock,
    MailMessageButtonBlock,
    OutboundOnlyAreaBlock,
    PrivateSwitchButtonBlock, 
    StaticRedirectAttribute,
    StaticRedirectAttributeLabel, 
    StaticTextLabel, 
    TaskAreaBlock,
    TaskStampButtonBlock,
)
    
