## FunctionalList1.py
## Author : Olivier Giroussens
## Description: This test suite runs the 4 basic testcases of generating event, mail, task and note items in chandler
 

import osaf.framework.QAUITestAppLib as QAUITestAppLib
import os

filePath = os.path.expandvars('$CATSREPORTDIR')
cats_home = os.path.expandvars('$CATSHOME')
if not os.path.exists(filePath):
    filePath = os.getcwd()


#initialization
fileName = "FunctionalTestList1.log"
logger = QAUITestAppLib.QALogger(os.path.join(filePath, fileName),"FunctionalTestList1")

#actions
execfile(os.path.join(cats_home,"QATestScripts/TestCreateAccounts.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestNewCollection.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestNewEvent.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestNewMail.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestNewTask.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestNewNote.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestCalView.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestSwitchingViews.py"))
execfile(os.path.join(cats_home,"QATestScripts/TestExporting.py"))
#cleaning
logger.Close()
