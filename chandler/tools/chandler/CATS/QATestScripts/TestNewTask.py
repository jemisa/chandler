import osaf.framework.QAUITestAppLib as QAUITestAppLib
import os

filePath = os.path.expandvars('$CATSREPORTDIR')
if not os.path.exists(filePath):
    filePath = os.getcwd()
    
#initialization
fileName = "TestNewTask.log"
logger = QAUITestAppLib.QALogger(os.path.join(filePath, fileName),"TestNewTask")
task = QAUITestAppLib.UITestItem("Task", logger)

#action
task.logger.Start("Setting Task attributes")
task.SetAttr(displayName="Task of sending birthday invites", body="Send birthday invitations")
task.logger.Stop()

#verification
task.Check_DetailView({"displayName":"Task of sending birthday invites","body":"Send birthday invitations"})

#cleaning
logger.Close()
