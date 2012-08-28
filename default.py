import xbmc, xbmcgui, xbmcaddon, xbmcplugin
import urllib, urllib2
import re, string
import os
from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
import urlresolver
from metahandler import metahandlers
import time
import elementtree.ElementTree as ET
import Queue
import threading

from utils import *

ADDON = Addon('plugin.video.watchseries.eu', sys.argv)
XADDON = xbmcaddon.Addon(id='plugin.video.watchseries.eu')
PROFILE_PATH = ADDON.get_profile()
DB_PATH = os.path.join(xbmc.translatePath('special://database'), 'watchseriescache.db')
NET = Net()

##### Path/URL Helpers #####
MAIN_URL = 'http://watchseries.eu'
ADDON_PATH = XADDON.getAddonInfo('path')
THEMEPATH = ADDON_PATH + '/resources/media/themes/'
IMG_PATH = THEMEPATH + '%s/%s'
SERIES_URL = MAIN_URL + '/letters/%s'
SEARCH_URL = MAIN_URL + '/search/%s'

##### Constants #####
APIKEY = '526B09725093425B'

##### Settings #####
USEMETA = ADDON.get_setting('usemetadata') == 'true'
SHOWPERCENT = ADDON.get_setting('showpercent') == 'true'
AUTOTRY = ADDON.get_setting('tryautoload') == 'true'
USECACHE = ADDON.get_setting('usecache') == 'true'
CACHETIME = 2**(1+int(ADDON.get_setting('cachetime')))
THREADCOUNT = int(ADDON.get_setting('threadcount'))
MAXRETRIES = int(ADDON.get_setting('maxretries'))
DEBUGMODE = ADDON.get_setting('debugmode') == 'true'
SEARCHTIME = int(ADDON.get_setting('searchcachetime'))

# This setting is set in function getThemes
THEME = 'default'

##### Diagnostic Information #####
Log('Starting up...', overrideDebug = True)
Log('Use meta: %s' % USEMETA)
Log('Thread count for meta: %d' % THREADCOUNT)
Log('Show percent: %s' % SHOWPERCENT)
Log('Auto try: %s' % AUTOTRY)
Log('Use Cache: %s' % USECACHE)
Log('Cache time %d hrs' % CACHETIME)
Log('Search time %d' % SEARCHTIME)
Log('Urlresolver Version: %s' % getAddonVersion('script.module.urlresolver'), overrideDebug = True)
Log('Watchseries.eu Version: %s' % getAddonVersion('plugin.video.watchseries.eu'), overrideDebug = True)

try:
    from sqlite3 import dbapi2 as sqlite
    Log('Loading sqlite3 as DB engine', overrideDebug = True)
except:
    from pysqlite2 import dbapi2 as sqlite
    Log('Loading pysqlite2 as DB engine', overrideDebug = True)

metaget = metahandlers.MetaData()
    
if not os.path.isdir(PROFILE_PATH):
    os.makedirs(PROFILE_PATH)
    
queue = Queue.Queue() 
queue2 = Queue.Queue()
imdbhosts = {}
metadict = {}
titlehosts = {}
yearhosts = {}

class ThreadIMDBGet(threading.Thread):
    
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        
    def run(self):
        while True:
            db = sqlite.connect(DB_PATH)
            host = self.queue.get()
            
            global imdbhosts
            
            cached = db.execute('SELECT * FROM imdb_cache WHERE url = ?', (host,)).fetchone()
            if cached:
                imdbhosts[host] = cached[1]
                db.close()
                self.queue.task_done()
                continue
            
            html = QueryWatchSeries(host, self.name)
            
            imdb_id = re.search('<a href="http://www.imdb.com/title/(.+?)/" target="_blank">IMDB</a>', html, re.DOTALL)
            
            if imdb_id:
                db.execute('INSERT OR REPLACE INTO imdb_cache (url, imdb_id) VALUES (?, ?)', (host, imdb_id.group(1)))
                db.commit()
                imdbhosts[host] = imdb_id.group(1)
            else:
                imdbhosts[host] = None
            db.close()    
            self.queue.task_done()
            
def getThemes():
    Log('getThemes Line:%s' % lineno())
    global THEME
    themelist = os.listdir(THEMEPATH)
    try:
        themelist.remove('default')
    except:
        pass
        
    themelist.insert(0, 'default')
    Log(themelist)
    
    try:
        tree = ET.parse(ADDON_PATH + '/resources/settings.xml')
        themeiter = tree.getiterator("setting")
        for t in themeiter:
            if t.attrib['id'] == 'theme':
                t.attrib['values'] = 'default'
                for th in themelist:
                    if not th == 'default':
                        t.attrib['values'] += '|' + th
        tree.write(ADDON_PATH + '/resources/settings.xml')  
        THEME = ADDON.get_setting('theme')
    except:
        pass
    
def initDatabase():
    if not os.path.isdir(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH))
        
    db = sqlite.connect(DB_PATH)
    db.execute('CREATE TABLE IF NOT EXISTS favorites (mode, name, url)')
    db.execute('CREATE TABLE IF NOT EXISTS imdb_cache (url UNIQUE, imdb_id)')
    db.execute('CREATE TABLE IF NOT EXISTS url_cache (url UNIQUE, response, timestamp)')
    db.execute('CREATE TABLE IF NOT EXISTS search (name, timestamp)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniquefav ON favorites (name, url)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniqueIMDBurl ON imdb_cache (url)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_url ON url_cache (url)')
    db.commit()
    db.close()
    
def GetUrl(url, threadName = None):
    '''
    Performs an url query and checks if it's already cached
    '''
    LogWithThread('GetUrl Line: %s' % lineno(), threadName = threadName, overrideDebug = True)
    url = re.sub(' ', '%20', url)
    LogWithThread('URL: %s' % url, threadName = threadName, overrideDebug = True)
    
    db = sqlite.connect(DB_PATH)
    now = time.time()
    if USECACHE:
        limit = 60*60*CACHETIME
        cached = db.execute('SELECT * FROM url_cache WHERE url = ?', (url,)).fetchone()
        if cached:
            created = int(cached[2])
            age = now - created
            if cached[1] != '':
                if age < limit:
                    LogWithThread('Return cached response for %s' % url, threadName = threadName, overrideDebug = True)
                    db.close()
                    return cached[1]
                else:
                    LogWithThread('Cached response too old. Request from internet.', threadName = threadName, overrideDebug = True)
            else:
                LogWithThread('Cached data empty. Trying to retrieve again.', threadName = threadName, overrideDebug = True)
        else:
            LogWithThread('No cached response. Request from internet.', threadName = threadName, overrideDebug = True)
            
    cnt = 0
    html = ''
    while not html and cnt < MAXRETRIES:
        cnt+=1
        try:
            html = NET.http_GET(url).content
        except:
            html = ''
            
    if not html:
        LogWithThread('theTVDB.com did not respond for url %s' % url, threadName = threadName, overrideDebug = True)
        
    #hack for unicode crap
    try:
        db.execute('INSERT OR REPLACE INTO url_cache (url, response, timestamp) VALUES (?, ?, ?)', (url, html, now))
    except:
        db.execute('INSERT OR REPLACE INTO url_cache (url, response, timestamp) VALUES (?, ?, ?)', (url, html.decode('utf-8'), now))
        
    db.commit()
    db.close()
        
    return html
    
class ThreadMeta(threading.Thread):
    
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        
    def run(self):
        while True:
            host = self.queue.get()
            
            if imdbhosts[host]:
                html = GetUrl('http://thetvdb.com/api/GetSeriesByRemoteID.php?imdbid=%s' % (imdbhosts[host]), threadName = self.name)
            else:
                html = GetUrl('http://thetvdb.com/api/GetSeries.php?seriesname=%s' % (titlehosts[host]), threadName = self.name)
                
            LogWithThread('HTMLHTMLHTMLHTML: %s' % html[:400], threadName = self.name)
            
            #dirty hack for unicode
            try:
                test = ET.fromstring(html)
            except:
                html = html.encode('utf-8')
                
            try:
                tree = ET.fromstring(html)
                node = tree.find('Series')
                seriesid = node.findtext('seriesid')
            except:
                seriesid = ''
                
            LogWithThread('SERIESID: %s' % seriesid, threadName = self.name, overrideDebug = True)
                
            if seriesid:
                html = GetUrl('http://thetvdb.com/api/%s/series/%s/en.xml' % (APIKEY, seriesid), threadName = self.name)
                
                #hack for unicode
                try:
                    test = ET.fromstring(html)
                except:
                    html = html.encode('utf-8')
                    
                try:
                    tree = ET.fromstring(html)
                    node = tree.find('Series')
                    metadict[host]['imdb_id'] = node.findtext('IMDB_ID')
                    metadict[host]['tvdb_id'] = seriesid
                    metadict[host]['title'] = node.findtext('SeriesName')
                    metadict[host]['TVShowTitle'] = metadict[host]['title']
                    
                    rating = node.findtext('Rating')
                    if str(rating) != '' and rating != None:
                        metadict[host]['rating'] = float(rating)
                    
                    metadict[host]['duration'] = node.findtext('Runtime')
                    metadict[host]['plot'] = node.findtext('Overview')
                    metadict[host]['mpaa'] = node.findtext('ContentRating')
                    metadict[host]['premiered'] = node.findtext('FirstAired')
                    metadict[host]['year'] = int(yearhosts[host])
                    
                    genre = node.findtext('Genre')
                    genre = genre.replace('|', ',')
                    genre = genre[1:(len(genre)-1)]
                    metadict[host]['genre'] = genre
                    
                    metadict[host]['studio'] = node.findtext('Network')
                    metadict[host]['status'] = node.findtext('Status')
                    
                    actors = [a for a in node.findtext('Actors').split("|") if a]
                    if actors:
                        metadict[host]['cast'] = []
                        for actor in actors:
                            metadict[host]['cast'].append(actor)
                            
                    temp = node.findtext('banner')
                    if temp != '' and temp is not None:  
                        metadict[host]['banner_url'] = 'http://www.thetvdb.com/banners/%s' % temp
                    else:
                        metadict[host]['banner_url'] = ''
                        
                    temp = node.findtext('poster')
                    if temp != '' and temp is not None:
                        metadict[host]['cover_url'] = 'http://www.thetvdb.com/banners/%s' % temp
                    else:
                        metadict[host]['cover_url'] = ''
                        
                    temp = node.findtext('fanart')
                    if temp != '' and temp is not None:
                        metadict[host]['backdrop_url'] = 'http://www.thetvdb.com/banners/%s' % temp
                    else:
                        metadict[host]['backdrop_url'] = ''
                        
                    metadict[host]['overlay'] = 6
                    
                except:
                    metadict[host]['title'] = titlehosts[host]
                    metadict[host]['cover_url'] = ''
                    metadict[host]['backdrop_url'] = ''
            else:    
                metadict[host]['title'] = titlehosts[host]
                metadict[host]['cover_url'] = ''
                metadict[host]['backdrop_url'] = ''
                
            LogWithThread('doublecheck: %s' % metadict[host]['title'], threadName = self.name)
            LogWithThread('doublecheck: %s' % metadict[host], threadName = self.name)
            
            self.queue.task_done()
    
def QueryWatchSeries(url, threadName = None):
    '''
    Sends an html query to watchseries. If the website
    is down (cant connect to db) gives error and backs out.
    
    '''
    LogWithThread('QueryWatchSeries Line: %s' % lineno(), threadName = threadName)
    url = re.sub(' ', '%20', url)    
    LogWithThread('URL: %s' % url, threadName = threadName)
    
    html = GetUrl(url, threadName = threadName)
        
    #ADDON.log('HTML: %s' % html[:100])
     
    match = re.search('cant connect to db', html, re.DOTALL)
    
    if match:
        ADDON.show_error_dialog(['Watchseries.eu is currently down.', '', 'Error returned: cant connect to db'])
        return None
    else:
        return html

def MainMenu():
    Log('Main Menu Line:%s' % lineno())
    ADDON.add_directory({'mode': 'tvaz'}, {'title':'All Series (A - Z)'}, img=IMG_PATH % (THEME, 'atoz.png'))
    ADDON.add_directory({'mode': 'search'}, {'title': 'Search...'}, img=IMG_PATH % (THEME, 'search.png'))
    ADDON.add_directory({'mode': 'favorites'}, {'title': 'Favorites'})
    ADDON.add_directory({'mode': 'latest', 'url': MAIN_URL + '/latest'}, {'title': 'Newest Episodes Added'})
    ADDON.add_directory({'mode': 'popular', 'url': MAIN_URL + '/new'}, {'title': 'This Weeks Popular Episodes'})
    ADDON.add_directory({'mode': 'schedule', 'url': MAIN_URL + '/tvschedule'}, {'title': 'TV Schedule'})
    ADDON.add_directory({'mode': 'genres', 'url': MAIN_URL + '/genres/'}, {'title': 'TV Shows Genres'}, img=IMG_PATH % (THEME, 'genres.png'))
    ADDON.end_of_directory()
    
def AZ_Menu():
    Log('AZ_Menu Line:%s' % lineno())
    ADDON.add_directory({'mode': 'tvseriesaz', 'url': SERIES_URL % '09'}, {'title': '0 - 9'}, img=IMG_PATH % (THEME, '123.png'))
    for l in string.ascii_uppercase:
        ADDON.add_directory({'mode': 'tvseriesaz', 'url': SERIES_URL % l}, {'title': l}, img=IMG_PATH % (THEME, l + '.png'))
    ADDON.end_of_directory()
    
def Search():
    Log('Search Line:%s' % lineno())
    db = sqlite.connect(DB_PATH)
    now = time.time()
    limit = 60*60*SEARCHTIME
    if SEARCHTIME == 13: limit = sys.maxint
    cached = db.execute('SELECT * FROM search').fetchone()
    oldsearch = ''
    
    if cached:
        created = int(cached[1])
        age = now - created
        if cached[0] != '' and cached[0] != None:
            if age < limit:
                oldsearch = cached[0]
    
    keyboard = xbmc.Keyboard()
    keyboard.setHeading('Search TV Shows')
    keyboard.setDefault(oldsearch)
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        search_text = keyboard.getText()
        db.execute('DELETE FROM search')        # delete all old search terms
        db.execute('INSERT OR REPLACE INTO search (name, timestamp) VALUES (?, ?)', (search_text, now))
        db.commit()
        db.close()
        Log('SEARCH TEXT: %s' % search_text, overrideDebug = True)
        # do search
        html = QueryWatchSeries(SEARCH_URL % search_text)
        
        numMatches = re.search('Found (.+?) matches.', html)
        if not numMatches:  # nothing found. alert user
            ADDON.show_error_dialog(['Sorry, No shows found.'])
            return
        
        numMatches = int(numMatches.group(1))
        nextpage = re.search('<a href="(.+?)"> Next Search Page</a>', html)
        matches = []
        
        loop = True
        while loop or nextpage:
            loop = False
            
            items = re.findall('<a href="(.+?)" title="watch serie.+?"><b>(.+?)</b></a>', html)
            for each in items:
                matches.append(each[0]+'#####'+each[1])
                
            if nextpage:
                url = nextpage.group(1)
                html = QueryWatchSeries(url)
                
                nextpage = re.search('<a href="(.+?)"> Next Search Page</a>', html)
                if not nextpage: loop = True
                    
        meta = {}
        
        for item in matches:
            parts = re.match('(.+?)#####(.+?)$', item)
            if parts:
                match = re.match('(.+?) \((.+?)\)$', parts.group(2))
                url = parts.group(1)
                title = match.group(1)
                year = match.group(2)
                Log(title)
                Log(year)
                
                if USEMETA:
                    meta = metaget.get_meta('tvshow', title)
                    Log(meta)
                else:
                    meta['title'] = title + ' (' + year + ')'
                    meta['cover_url'] = ''
                    meta['backdrop_url'] = ''
                    
                cm = []
                cm.append(('Show Information', 'XBMC.Action(Info)'))
                cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvseasons', meta['title'], url)))
                cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
          
                ADDON.add_directory({'mode': 'tvseasons', 'url': url}, meta, contextmenu_items=cm, context_replace=True, img=meta['cover_url'], fanart=meta['backdrop_url'], total_items=numMatches)
        ADDON.end_of_directory()  
    else: db.close()
        
def Get_Favorites():
    Log('Get_Favorites Line:%s' % lineno())
    
    db = sqlite.connect(DB_PATH)
    cursor = db.cursor()
    
    favorites = cursor.execute('SELECT mode, name, url FROM favorites ORDER BY name')
    for row in favorites:
        storemode = row[0]
        name = row[1]
        link = row[2]
        
        Log('STOREMODE: %s' % storemode)
        Log('NAME: %s' % name)
        Log('LINK: %s' % link)
        
        cm = []
        cm.append(('Remove from Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=remove_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], storemode, urllib.unquote_plus(name), link)))
        
        ADDON.add_directory({'mode': storemode, 'url': link}, {'title': name}, contextmenu_items=cm, context_replace=True)
    ADDON.end_of_directory()
    
def Add_Favorite():
    Log('Add_Favorite Line:%s' % lineno())
    
    db = sqlite.connect(DB_PATH)
    cursor = db.cursor()
    statement = 'INSERT INTO favorites (mode, name, url) VALUES (?, ?, ?)'
    try:
        cursor.execute(statement, (storemode, urllib.unquote_plus(name), url))
        xbmc.executebuiltin('XBMC.Notification(Save Favorite, Added to Favorites, 2000)')
    except sqlite.IntegrityError:
        xbmc.executebuiltin('XBMC.Notification(Save Favorite, Item already in Favorites, 2000)')
    db.commit()
    db.close()
    
def Remove_Favorite():
    Log('Remove_Favorite Line:%s' % lineno())
    
    Log('STOREMODE: %s' % storemode)
    Log('NAME: %s' % name)
    Log('URL: %s' % url)
    
    Log('Deleting Favorite: %s' % name)
    db = sqlite.connect(DB_PATH)
    cursor = db.cursor()
    cursor.execute('DELETE FROM favorites WHERE name=? AND url=?', (name, url))
    xbmc.executebuiltin('XBMC.Notification(Remove Favorite, Removed from Favorites, 2000)')
    db.commit()
    db.close()
    xbmc.executebuiltin('Container.Refresh')
            
def Get_Video_List():
    Log('Get_Video_List Line:%s' % lineno())
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
    
    match = re.findall('\t <li><a href="(.+?)" title="(.+?)">.+?<span class="epnum">(.+?)</span></a></li>', html, re.DOTALL)
    
    total = len(match)
    
    meta = {}
    
    if USEMETA:
        for i in range(THREADCOUNT):
            t = ThreadIMDBGet(queue)
            t.setDaemon(True)
            t.start()
            
        for link, title, year in match:
            queue.put(link)
            titlehosts[link] = title
            yearhosts[link] = year
            metadict[link] = {}
            
        queue.join()
        
        for i in range(THREADCOUNT):
            t = ThreadMeta(queue2)
            t.setDaemon(True)
            t.start()
            
        #print imdbhosts
        for link in imdbhosts:
            queue2.put(link)            
            
        queue2.join()
        
        Log('Metadict: %s' % metadict)
        
    for link, title, year in match:
        if USEMETA:
            meta = metadict[link]
        else:
            meta['title'] = title + ' (' + year + ')'
            meta['cover_url'] = ''
            meta['backdrop_url'] = ''
            
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvseasons', meta['title'], link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
        
        
        ADDON.add_directory({'mode': 'tvseasons', 'url': link}, meta, contextmenu_items=cm, context_replace=True, img=meta['cover_url'], fanart=meta['backdrop_url'], total_items=total)
    ADDON.end_of_directory()
            
def Get_Season_List():
    Log('Get_Season_List Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
    
    meta = {}
    
    match = re.findall('<h2 class="lists"><a href="(.+?)">(.+?)  (.+?)</a> - ', html)
    
    try:
        meta['imdb_id'] = re.search('<a href="http://www.imdb.com/title/(.+?)/" target="_blank">IMDB</a>', html, re.DOTALL).group(1)
    except:
        meta['imdb_id'] = ''
        
    #seasons = re.findall('<h2 class="lists"><a href=".+?">Season ([0-9]+)  .+?</a> -', html)
    num = 0
    for link, season, episodes in match:
        queries = {'mode': 'tvepisodes', 'url': link, 'imdb_id':meta['imdb_id'], 'season': num + 1}
            
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvepisodes', season + ' ' + episodes, link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
        
        ADDON.add_directory(queries, {'title': season + ' ' + episodes}, contextmenu_items=cm, context_replace=True, total_items=len(match))
        num += 1
    ADDON.end_of_directory()
        
def Get_Episode_List():
    Log('Get_Episode_List Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
        
    match = re.findall('<li><a href="\..(.+?)"><span class="">.+?. Episode (.+?)&nbsp;&nbsp;&nbsp;(.*?)</span><span class="epnum">(.+?)</span></a>', html, re.DOTALL)
    
    for link, episode, name, aired in match:
        if name == '' or name == None:
            name = 'Episode ' + str(episode)
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'sources', episode + ' ' + name + ' (' + aired + ')', MAIN_URL + link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
        ADDON.add_directory({'mode': 'sources', 'url': MAIN_URL + link}, {'title': episode + ' ' + name + ' (' + aired + ')'}, contextmenu_items=cm, context_replace=True, total_items=len(match))
    ADDON.end_of_directory()
    
def Get_Sources():
    Log('Get_Sources Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    NET.save_cookies(PROFILE_PATH + 'cookie.txt')
    
    try:
        title = re.search('<span class="list-top"><a href="http://watchseries.eu/.+?">.+?</a> (.+?)</span>', html).group(1)
    except:
        title = 'unknown'
    
    showid = re.search('-(.+?).html', url).group(1)
    
    html = QueryWatchSeries(MAIN_URL + '/getlinks.php?q=' + showid + '&domain=all')
    Log('HTML: %s' % html[:100])
    
    hosts = re.finditer('<div class="site">\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t(.+?)\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t</div>\r\n\t\t\t\t\t\t\t\t\t\t\t\t<div class="siteparts">\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t<a href="..(.+?)" target="_blank".+?class="user">(.+?)</div>', html, re.DOTALL)
    sources = []
    sourceData = []
    
    num = 0
    for s in hosts:
        host, link, percent = s.groups()
        
        if SHOWPERCENT:
            dispTitle = host + ' - ' + percent
        else:
            dispTitle = host
        
        hosted_media = urlresolver.HostedMediaFile(host=host, media_id='xxx'+str(num), title=dispTitle)
        if hosted_media:
            num+=1
            sources.append(hosted_media)
            sourceData.append(link)
    
    if num == 0:
        ADDON.show_error_dialog(['Sorry, no sources found.'])
        return
    else:
        notplayed = True
        curSourceIndex = -1
        while notplayed:
            curSourceIndex += 1
            Log('NUM: %s' % str(num))
            if AUTOTRY: 
                Log('cursourceindex: %s' % str(curSourceIndex))
                
                if curSourceIndex == num:   # exhausted sources
                    source = None
                    ADDON.show_error_dialog(['Sorry, no sources could play file.'])
                else:
                    source = sources[curSourceIndex]
            else:
                source = urlresolver.choose_source(sources)
            if source:
                index = int(re.match('xxx(.+?)', source.get_media_id()).group(1))
                Log('Index: %s' % str(index))
                Log('Link: %s' % sourceData[index])
                
                html = QueryWatchSeries(MAIN_URL + sourceData[index])
                
                match = re.search('\r\n\t\t\t\t<a href="(.+?)" class="myButton">', html).group(1)
                Log('MATCH: %s' % match + lineno())
                
                try:
                    post_url = NET.http_GET(match).get_url()
                except:
                    post_url = '404'
            
                Log('POST_URL: %s' % post_url)
                
                try:
                    error = re.findall('404', post_url)[0]
                except:
                    error = ''
            
                if error != '':
                    if not AUTOTRY: ADDON.show_error_dialog(['Sorry, File has been deleted from host.', '', 'Try another host.'])
                else:
                    try:
                        stream_url = urlresolver.HostedMediaFile(post_url).resolve()
                        Log('STREAM_URL: %s' % stream_url)                  
                        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                        playlist.clear()
                        listitem = xbmcgui.ListItem(title)
                        playlist.add(url=stream_url, listitem=listitem)
                        notplayed = False
                        xbmc.Player(xbmc.PLAYER_CORE_DVDPLAYER).play(playlist)
                    except:
                        if num == 1:
                            notplayed = False
                            ADDON.show_error_dialog(['Sorry, no sources could play file.'])
                        else:
                            notplayed = True
                            if not AUTOTRY: ADDON.show_error_dialog(['That source cannot be resolved.','','Please choose another source.'])
            else:
                notplayed = False
   
def Get_Latest():
    Log('Get_Latest Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
        
    matches = re.findall('\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t<li><a href="(.+?)" title=".+?">(.+?)</a></li>', html, re.DOTALL)
    total = len(matches)
    for link, title in matches:
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'sources', title, link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
        ADDON.add_directory({'mode': 'sources', 'url': link}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=total)
    ADDON.end_of_directory()
    
def Get_Popular():
    Log('Get_Popular Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
        
    matches = re.findall('\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t<li><a href="(.+?)" title=".+?">(.+?)</a></li>', html, re.DOTALL)
    
    for link, title in matches:
        r = re.search('(.+?).html',link,re.DOTALL)
        
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        
        if r:
            cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'sources', title, link)))
            cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
            ADDON.add_directory({'mode': 'sources', 'url': link}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
        else:
            cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvepisodes', title, link)))
            cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
            ADDON.add_directory({'mode': 'tvepisodes', 'url': link}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
    ADDON.end_of_directory()
    
def Get_Schedule():
    Log('Get_Schedule Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
        
    matches = re.findall('<li><a href="http://watchseries.eu/tvschedule/(.+?)">(.+?)</a></li>', html, re.DOTALL)
    for link, title in matches:
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'schedule_list', title, MAIN_URL + '/tvschedule/'+link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
        
        ADDON.add_directory({'mode': 'schedule_list', 'url': MAIN_URL + '/tvschedule/'+link}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
    ADDON.end_of_directory()
    
def Get_Schedule_List():
    Log('Get_Schedule_List Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    Log('HTML: %s' % html[:100])
        
    matches = re.findall('\t \t\t\t\t\t\t\t\t\t\t\t\t\t <a href="(.+?)>(.+?)</a>\r\n', html, re.DOTALL)
    for link, title in matches:
        match = re.findall('(.+?)"', link, re.DOTALL)[0]
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        
        if match == '#':
            cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'schedule_none', title, MAIN_URL + '/tvschedule/'+match)))
            cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
            ADDON.add_directory({'mode': 'schedule_none', 'url': MAIN_URL + '/tvschedule/'+match}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
        else:
            cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvseasons', title, match)))
            cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
            ADDON.add_directory({'mode': 'tvseasons', 'url': match}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
    ADDON.end_of_directory()
    
def Get_Genres():
    Log('Get_Genres Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url+'action')
    Log('HTML: %s' % html[:100])
    
    genres = re.findall('<a href="http://watchseries.eu/genres/.+?">(.+?)</a>', html, re.DOTALL)
    genres.sort()
    for g in genres:
        if g[0].islower():
            title = g.capitalize()
            cm = []
            cm.append(('Show Information', 'XBMC.Action(Info)'))
            cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'genresList', title, url + g)))
            cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
            
            ADDON.add_directory({'mode': 'genresList', 'url': url + g}, {'title': title}, contextmenu_items=cm, context_replace=True)
    ADDON.end_of_directory()
    
def Get_Genre_List():
    Log('Get_Genre_List Line:%s' % lineno())
    
    Log('URL: %s' % url)
    html = QueryWatchSeries(url)
    
    matches = re.findall('\t\t\t <li><a href="(.+?)\n" title="Watch .+? Online">(.+?)<span class="epnum">(.+?)</span></a></li>', html, re.DOTALL)
    total = len(matches)
    for link, title, year in matches:
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'tvseasons', title + ' (' + year + ')', link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
        
        ADDON.add_directory({'mode': 'tvseasons', 'url': link}, {'title': title + ' (' + year + ')'}, contextmenu_items=cm, context_replace=True, total_items=total)
    ADDON.end_of_directory()

def GetParams():
    '''
    Code by Bstrdsmkr from 1channel plugin
    '''
    param=[]
    paramstring=sys.argv[len(sys.argv)-1]
    if len(paramstring)>=2:
        cleanedparams=paramstring.replace('?','')
        if (paramstring[len(paramstring)-1]=='/'):
                paramstring=paramstring[0:len(paramstring)-2]
        pairsofparams=cleanedparams.split('&')
        param={}
        for i in range(len(pairsofparams)):
            splitparams={}
            splitparams=pairsofparams[i].split('=')
            if (len(splitparams))==2:
                param[splitparams[0]]=splitparams[1]			
    return param

Log('BEFORE GETPARAMS: %s' % sys.argv)
params=GetParams()

initDatabase()
getThemes()

try:    mode = params['mode']
except: mode = 'main'
try:    url = urllib.unquote(params['url'])
except: url = None
try:    name = params['title']
except: name = None
try:    storemode = params['storemode']
except: storemode = None
        
if mode=='main':
    MainMenu()
elif mode=='tvaz':
    AZ_Menu()
elif mode=='search':
    Search()
elif mode=='favorites':
    Get_Favorites()
elif mode=='add_favorite':
    Add_Favorite()
elif mode=='remove_favorite':
    Remove_Favorite()
elif mode=='tvseriesaz':
    Get_Video_List()
elif mode=='tvseasons':
    Get_Season_List()
elif mode=='tvepisodes':
    Get_Episode_List()
elif mode=='sources':
    Get_Sources()
elif mode=='latest':
    Get_Latest()
elif mode=='popular':
    Get_Popular()
elif mode=='schedule':
    Get_Schedule()
elif mode=='schedule_list':
    Get_Schedule_List()
elif mode=='genres':
    Get_Genres()
elif mode=='genresList':
    Get_Genre_List()
elif mode=='settings':
    ADDON.show_settings()
elif mode=='metapath':
    import metahandler
    metahandler.display_settings()
elif mode=='loadThemes':
    xbmc.executebuiltin('XBMC.Notification(Load Themes, Loaded themes, 2000)')
    time.sleep(2)
    xbmc.executebuiltin("Dialog.Close(all,true)")
    ADDON.show_settings()
elif mode=='resetCache':
    db = sqlite.connect(DB_PATH)
    db.execute('DELETE FROM imdb_cache')
    db.execute('DELETE FROM url_cache')
    db.commit()
    db.close()
    xbmc.executebuiltin('XBMC.Notification(Reset Cache, Successfully resetted cache, 2000)')