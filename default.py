import xbmc, xbmcgui, xbmcaddon, xbmcplugin
import urllib, urllib2
import re, string
import os
from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
import urlresolver
from metahandler import metahandlers
import inspect
import time
import elementtree.ElementTree as ET

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

##### Settings #####
USEMETA = ADDON.get_setting('usemetadata') == 'true'
SHOWPERCENT = ADDON.get_setting('showpercent') == 'true'
AUTOTRY = ADDON.get_setting('tryautoload') == 'true'

THEMELIST = []
THEME = 'default'

ADDON.log('Starting up...')

metaget = metahandlers.MetaData()

try:
    from sqlite3 import dbapi2 as sqlite
    ADDON.log('Loading sqlite3 as DB engine')
except:
    from pysqlite2 import dbapi2 as sqlite
    ADDON.log('Loading pysqlite2 as DB engine')
    
if not os.path.isdir(PROFILE_PATH):
    os.makedirs(PROFILE_PATH)
    
def lineno():
    """Returns the current line number in our program."""
    return ' %s' % str(inspect.currentframe().f_back.f_lineno)

def getThemes():
    ADDON.log('getThemes Line:%s' % lineno())
    global THEMELIST
    global THEME
    THEMELIST = os.listdir(THEMEPATH)
    try:
        THEMELIST.remove('default')
    except:
        pass
        
    THEMELIST.insert(0, 'default')
    ADDON.log(THEMELIST)
    
    try:
        tree = ET.parse(ADDON_PATH + '/resources/settings.xml')
        themeiter = tree.getiterator("setting")
        for t in themeiter:
            if t.attrib['id'] == 'theme':
                t.attrib['values'] = 'default'
                for TH in THEMELIST:
                    if not TH == 'default':
                        t.attrib['values'] += '|' + TH
        tree.write(ADDON_PATH + '/resources/settings.xml')  
        THEME = THEMELIST[int(ADDON.get_setting('theme'))]                    
    except:
        pass
    
    
def initDatabase():
    if not os.path.isdir(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH))
        
    db = sqlite.connect(DB_PATH)
    db.execute('CREATE TABLE IF NOT EXISTS favorites (mode, name, url)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniquefav ON favorites (name, url)')
    db.execute('CREATE TABLE IF NOT EXISTS imdb_cache (name, year, imdb_id)')
    db.commit()
    db.close()
    

   
def QueryWatchSeries(url):
    '''
    Sends an html query to watchseries. If the website
    is down (cant connect to db) gives error and backs out.
    
    '''
    ADDON.log('QueryWatchSeries Line: %s' % lineno())
    url = re.sub(' ', '%20', url)
    
    ADDON.log('URL: %s' % url)
    
    try:
        html = NET.http_GET(url).content
    except:
        html = ''
        
    ADDON.log('HTML: %s' % html[:100])
     
    match = re.search('cant connect to db', html, re.DOTALL)
    
    if match:
        ADDON.show_error_dialog(['Watchseries.eu is currently down.', '', 'Error returned: cant connect to db'])
        return None
    else:
        return html

def MainMenu():
    ADDON.log('Main Menu Line:%s' % lineno())
    ADDON.add_directory({'mode': 'tvaz'}, {'title':'All Series (A - Z)'}, img=IMG_PATH % (THEME, 'atoz.png'))
    ADDON.add_directory({'mode': 'search'}, {'title': 'Search...'}, img=IMG_PATH % (THEME, 'search.png'))
    ADDON.add_directory({'mode': 'favorites'}, {'title': 'Favorites'})
    ADDON.add_directory({'mode': 'latest', 'url': MAIN_URL + '/latest'}, {'title': 'Newest Episodes Added'})
    ADDON.add_directory({'mode': 'popular', 'url': MAIN_URL + '/new'}, {'title': 'This Weeks Popular Episodes'})
    ADDON.add_directory({'mode': 'schedule', 'url': MAIN_URL + '/tvschedule'}, {'title': 'TV Schedule'})
    ADDON.add_directory({'mode': 'genres', 'url': MAIN_URL + '/genres/'}, {'title': 'TV Shows Genres'}, img=IMG_PATH % (THEME, 'genres.png'))
    ADDON.end_of_directory()
    
def AZ_Menu():
    ADDON.log('AZ_Menu Line:%s' % lineno())
    ADDON.add_directory({'mode': 'tvseriesaz', 'url': SERIES_URL % '09'}, {'title': '0 - 9'}, img=IMG_PATH % (THEME, '123.png'))
    for l in string.ascii_uppercase:
        ADDON.add_directory({'mode': 'tvseriesaz', 'url': SERIES_URL % l}, {'title': l}, img=IMG_PATH % (THEME, l + '.png'))
    ADDON.end_of_directory()
    
def Search():
    ADDON.log('Search Line:%s' % lineno())
    
    keyboard = xbmc.Keyboard()
    keyboard.setHeading('Search TV Shows')
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        search_text = keyboard.getText()
        ADDON.log('SEARCH TEXT: %s' % search_text)
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
                ADDON.log(title)
                ADDON.log(year)
                
                if USEMETA:
                    meta = metaget.get_meta('tvshow', title)
                    ADDON.log(meta)
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
        
def Get_Favorites():
    ADDON.log('Get_Favorites Line:%s' % lineno())
    
    db = sqlite.connect(DB_PATH)
    cursor = db.cursor()
    
    favorites = cursor.execute('SELECT mode, name, url FROM favorites ORDER BY name')
    for row in favorites:
        storemode = row[0]
        name = row[1]
        link = row[2]
        
        ADDON.log('STOREMODE: %s' % storemode)
        ADDON.log('NAME: %s' % name)
        ADDON.log('LINK: %s' % link)
        
        cm = []
        cm.append(('Remove from Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=remove_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], storemode, urllib.unquote_plus(name), link)))
        
        ADDON.add_directory({'mode': storemode, 'url': link}, {'title': name}, contextmenu_items=cm, context_replace=True)
    ADDON.end_of_directory()
    
def Add_Favorite():
    ADDON.log('Add_Favorite Line:%s' % lineno())
    
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
    ADDON.log('Remove_Favorite Line:%s' % lineno())
    
    ADDON.log('STOREMODE: %s' % storemode)
    ADDON.log('NAME: %s' % name)
    ADDON.log('URL: %s' % url)
    
    ADDON.log('Deleting Favorite: %s' % name)
    db = sqlite.connect(DB_PATH)
    cursor = db.cursor()
    cursor.execute('DELETE FROM favorites WHERE name=? AND url=?', (name, url))
    xbmc.executebuiltin('XBMC.Notification(Remove Favorite, Removed from Favorites, 2000)')
    db.commit()
    db.close()
    xbmc.executebuiltin('Container.Refresh')
            
def Get_Video_List():
    ADDON.log('Get_Video_List Line:%s' % lineno())
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
    
    match = re.findall('\t <li><a href="(.+?)" title="(.+?)">.+?<span class="epnum">(.+?)</span></a></li>', html, re.DOTALL)
    
    meta = {}
    
    total = len(match)
    for link, title, year in match:
        key = string.lower(re.sub(' ', '', title))
        key = re.sub('-', '', key)
        key = re.sub(',', '', key)
        key = re.sub('\(', '', key)
        key = re.sub('\)', '', key)
        
        ADDON.log('KEY : %s' % key)
        
        if USEMETA:
            try:
                meta = metaget.get_meta('tvshow', title)
            except:
                meta['title'] = title + ' (' + year + ')'
                meta['cover_url'] = ''
                meta['backdrop_url'] = ''
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
    ADDON.log('Get_Season_List Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
    
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
    ADDON.log('Get_Episode_List Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
        
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
    ADDON.log('Get_Sources Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    NET.save_cookies(PROFILE_PATH + 'cookie.txt')
    
    try:
        title = re.search('<span class="list-top"><a href="http://watchseries.eu/.+?">.+?</a> (.+?)</span>', html).group(1)
    except:
        title = 'unknown'
    
    showid = re.search('-(.+?).html', url).group(1)
    
    html = QueryWatchSeries(MAIN_URL + '/getlinks.php?q=' + showid + '&domain=all')
    ADDON.log('HTML: %s' % html[:100])
    
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
            ADDON.log('NUM: %s' % str(num))
            if AUTOTRY: 
                ADDON.log('cursourceindex: %s' % str(curSourceIndex))
                
                if curSourceIndex == num:   # exhausted sources
                    source = None
                    ADDON.show_error_dialog(['Sorry, no sources could play file.'])
                else:
                    source = sources[curSourceIndex]
            else:
                source = urlresolver.choose_source(sources)
            if source:
                index = int(re.match('xxx(.+?)', source.get_media_id()).group(1))
                ADDON.log('Index: %s' % str(index))
                ADDON.log('Link: %s' % sourceData[index])
                
                html = QueryWatchSeries(MAIN_URL + sourceData[index])
                
                match = re.search('\r\n\t\t\t\t<a href="(.+?)" class="myButton">', html).group(1)
                ADDON.log('MATCH: %s' % match + lineno())
                
                try:
                    post_url = NET.http_GET(match).get_url()
                except:
                    post_url = '404'
            
                ADDON.log('POST_URL: %s' % post_url)
                
                try:
                    error = re.findall('404', post_url)[0]
                except:
                    error = ''
            
                if error != '':
                    if not AUTOTRY: ADDON.show_error_dialog(['Sorry, File has been deleted from host.', '', 'Try another host.'])
                else:
                    try:
                        stream_url = urlresolver.HostedMediaFile(post_url).resolve()
                        ADDON.log('STREAM_URL: %s' % stream_url)                  
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
    ADDON.log('Get_Latest Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
        
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
    ADDON.log('Get_Popular Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
        
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
    ADDON.log('Get_Schedule Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
        
    matches = re.findall('<li><a href="http://watchseries.eu/tvschedule/(.+?)">(.+?)</a></li>', html, re.DOTALL)
    for link, title in matches:
        cm = []
        cm.append(('Show Information', 'XBMC.Action(Info)'))
        cm.append(('Add to Favorites', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=add_favorite&storemode=%s&title=%s&url=%s)' % (sys.argv[1], 'schedule_list', title, MAIN_URL + '/tvschedule/'+link)))
        cm.append(('Add-on Settings', 'RunScript(plugin.video.watchseries.eu, %s, ?mode=settings)' % (sys.argv[1])))
        
        ADDON.add_directory({'mode': 'schedule_list', 'url': MAIN_URL + '/tvschedule/'+link}, {'title': title}, contextmenu_items=cm, context_replace=True, total_items=len(matches))
    ADDON.end_of_directory()
    
def Get_Schedule_List():
    ADDON.log('Get_Schedule_List Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url)
    ADDON.log('HTML: %s' % html[:100])
        
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
    ADDON.log('Get_Genres Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
    html = QueryWatchSeries(url+'action')
    ADDON.log('HTML: %s' % html[:100])
    
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
    ADDON.log('Get_Genre_List Line:%s' % lineno())
    
    ADDON.log('URL: %s' % url)
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

ADDON.log('BEFORE GETPARAMS: %s' % sys.argv)
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