import tools.QAUITestAppLib as QAUITestAppLib
import os
import osaf.pim as pim

App_ns = app_ns()

# initialization
fileName = "LargeDataBackupRepository.log"
logger = QAUITestAppLib.QALogger(fileName, "Backing up 3000 event repository")

name = 'Generated3000'

try:
    # import
    QAUITestAppLib.UITestView(logger, u'%s.ics' % name)
    
    # verification of import
    def VerifyEventCreation(title):
        global logger
        global App_ns
        global pim
        testEvent = App_ns.item_named(pim.CalendarEvent, title)
        if testEvent is not None:
            logger.ReportPass("Testing event creation: '%s'" % title)
        else:
            logger.ReportFailure("Testing event creation: '%s' not created" % title)
    
    VerifyEventCreation("Go to the beach")
    VerifyEventCreation("Basketball game")
    VerifyEventCreation("Visit friend")
    VerifyEventCreation("Library")
    
    # Current tests measure the first time you switch or overlay.
    # If you want to measure the subsequent times, enable this section.
    if 0:
        User.emulate_sidebarClick(App_ns.sidebar, name,  overlay=False)
        User.idle()
        User.emulate_sidebarClick(App_ns.sidebar, "All",  overlay=False)
        User.idle()
        User.emulate_sidebarClick(App_ns.sidebar, name,  overlay=True)
        User.idle()
        User.emulate_sidebarClick(App_ns.sidebar, name,  overlay=True)
        User.idle()
        
    # backup
    # - need to commit first so that the collection in the sidebar
    #   gets saved
    App_ns.itsView.commit()
    logger.Start("Backup repository")
    dbHome = App_ns.itsView.repository.backup()
    logger.Stop()
    
    # verification of backup
    if os.path.isdir(dbHome):
        logger.ReportPass("Backup exists")
    else:
        logger.ReportFailure("Backup does not exist")
    
    logger.SetChecked(True)
    logger.Report("Backup")

finally:
    # cleaning
    logger.Close()
