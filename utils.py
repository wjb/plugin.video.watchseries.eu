import elementtree.ElementTree as ET
import os
import xbmc
import inspect
import sys
from t0mm0.common.addon import Addon

ADDON = Addon('plugin.video.watchseries.eu', sys.argv)

DEBUGMODE = ADDON.get_setting('debugmode') == 'true'

def lineno():
    """Returns the current line number in our program."""
    return ' %s' % str(inspect.currentframe().f_back.f_lineno)

def LogWithThread(message, threadName = None):
    if not DEBUGMODE:
        return
        
    if threadName:
        ADDON.log('%s - %s' % (threadName, message))
    else:
        ADDON.log(message)
        
def Log(message):
    LogWithThread(message)

def getAddonVersion(addonName):
    path = os.path.join(xbmc.translatePath('special://home'), 'addons\\%s\\addon.xml' % addonName)

    try:
        tree = ET.parse(path)
        root = tree.getroot()
        ver = root.attrib['version']
    except:
        ver = 'x.x.x'
        
    return ver
