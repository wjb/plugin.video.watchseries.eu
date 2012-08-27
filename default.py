"""
    Watchseries.eu XBMC Video Addon
    Copyright (C) 2011 rogerThis
    Copyright (C) 2012 mscreations

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import xbmc, xbmcgui, xbmcaddon, xbmcplugin
import urllib, urllib2
import re, string
from xml.dom.minidom import parseString
from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
import urlresolver

addon = Addon('plugin.video.watchseries.eu', sys.argv)
xaddon = xbmcaddon.Addon(id='plugin.video.watchseries.eu')
net = Net()
profile_path = addon.get_profile()

apikey = '526B09725093425B'
domData = None          # Used for episode DOM
domData2 = None         # Used for banner DOM

##### Queries ##########
play = addon.queries.get('play', None)
mode = addon.queries['mode']
section = addon.queries.get('section', None)
url = addon.queries.get('url', None)
imdb_id = addon.queries.get('imdb_id', None)
show = addon.queries.get('show', None)

print 'Mode: ' + str(mode)
print 'Play: ' + str(play)
print 'URL: ' + str(url)
print 'Section: ' + str(section)
print 'IMDB ID: ' + str(imdb_id)
print 'Show: ' + str(show)

################### Global Constants #################################

main_url = 'http://watchseries.eu'
episode_url = main_url + 'episodes.php?e=%s&c=%s'
addon_path = xaddon.getAddonInfo('path')
#icon_path = addon_path + "/icons/"

######################################################################

if not os.path.isdir(profile_path):
     os.mkdir(profile_path)

### Create A-Z Menu
def AZ_Menu(type, url):
     
    addon.add_directory({'mode': type,
                         'url': main_url + url % '09',
                         'section': section,
                         'letter': '09'},{'title': '09'},
                         img='')
    for l in string.uppercase:
        addon.add_directory({'mode': type,
                             'url': main_url + url % l,
                             'section': section,
                             'letter': l}, {'title': l},
                             img='')

                             
def get_latest(url):
    html = net.http_GET(url).content
    
    match = re.compile('\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t<li><a href="(.+?)" title=".+?">(.+?)</a></li>',re.DOTALL).findall(html)
    total = len(match)
    for link, title in match:
        r = re.search('(.+?).html',link,re.DOTALL)#.group(1)
        #print r
        #match = re.compile('(.+?).html',re.DOTALL).findall(link)[0]
        if r:
            addon.add_directory({'mode': 'hosting_sites', 'url': link, 'section': 'tv'}, {'title': title}, total_items=total)
        else:
            addon.add_directory({'mode': 'tvepisodes', 'url': link, 'section': 'tv'}, {'title': title}, total_items=total)
    addon.end_of_directory()

def BrowseByGenreMenu(url): 
    html = net.http_GET(main_url + '/genres/action').content
    
    genres = re.findall('<a href="http://watchseries.eu/genres/.+?">(.+?)</a>', html, re.DOTALL)
    print 'Browse by genres screen'
    genres.sort()
    for g in genres:
        if g[0].islower():
            title = g.capitalize()
            addon.add_directory({'mode': 'genresList', 'url': url+g, 'section': 'tv'}, {'title': title})
    addon.end_of_directory()

def setupSeries(seriesid):
    if not seriesid: return 'none'
    global domData
    global domData2
    
    print 'FETCHING FROM THETVDB.COM'
    
    file = urllib2.urlopen('http://www.thetvdb.com/api/'+apikey+'/series/'+seriesid+'/all/en.xml')
    data = file.read()
    file.close()
    domData = parseString(data)

    file = urllib2.urlopen('http://www.thetvdb.com/api/'+apikey+'/series/'+seriesid+'/banners.xml')
    data = file.read()
    file.close()
    domData2 = parseString(data)

def get_FanArt(seriesid):
    if not seriesid: return 'none'
    global domData2
    if domData2 is None:
        setupSeries(seriesid)
    elif domData.getElementsByTagName('Series')[0].getElementsByTagName('id')[0].childNodes[0].nodeValue != seriesid:
        setupSeries(seriesid)

    try:
        return 'http://www.thetvdb.com/banners/' + domData2.getElementsByTagName('Banner')[0].getElementsByTagName('BannerPath')[0].childNodes[0].nodeValue
    except:
        pass

def get_Season_Art(seriesid, season):
    if not seriesid: return 'none'
    global domData2
    if domData2 is None:
        setupSeries(seriesid)
    elif domData.getElementsByTagName('Series')[0].getElementsByTagName('id')[0].childNodes[0].nodeValue != seriesid:
        setupSeries(seriesid)

    seas = domData2.getElementsByTagName('Banner')

    for x in seas:
        try:
            if x.getElementsByTagName('Season')[0].childNodes[0].nodeValue == season:
                return 'http://www.thetvdb.com/banners/' + x.getElementsByTagName('BannerPath')[0].childNodes[0].nodeValue
        except:
            pass

def get_Episode_Data(seriesid, season, episode):
    if not seriesid: return {'name':'',
                             'season':'',
                             'episode':'',
                             'filename':'',
                             'firstaired':'',
                             'overview':''}
    global domData
    if domData is None:
        setupSeries(seriesid)
    elif domData.getElementsByTagName('Series')[0].getElementsByTagName('id')[0].childNodes[0].nodeValue != seriesid:
        setupSeries(seriesid)

    episodes = domData.getElementsByTagName('Episode')

    for ep in episodes:
        try:
            if ep.getElementsByTagName('SeasonNumber')[0].childNodes[0].nodeValue == season:
                if ep.getElementsByTagName('EpisodeNumber')[0].childNodes[0].nodeValue == episode:
                    print ep.getElementsByTagName('EpisodeName')[0].childNodes[0].nodeValue
                    output = {'name': ep.getElementsByTagName('EpisodeName')[0].childNodes[0].nodeValue,
                              'season': ep.getElementsByTagName('SeasonNumber')[0].childNodes[0].nodeValue,
                              'episode': ep.getElementsByTagName('EpisodeNumber')[0].childNodes[0].nodeValue,
                              'filename': 'http://www.thetvdb.com/banners/' + ep.getElementsByTagName('filename')[0].childNodes[0].nodeValue,
                              'firstaired': ep.getElementsByTagName('FirstAired')[0].childNodes[0].nodeValue,
                              'overview': ep.getElementsByTagName('Overview')[0].childNodes[0].nodeValue.encode('ascii', 'xmlcharrefreplace')}
                    return output
        except:
            pass
        
def get_video_list(url):
    print 'get_video_list'
    html = net.http_GET(url).content
    match = re.compile('\t <li><a href="(.+?)" title="(.+?)">.+?<span class="epnum">(.+?)</span></a></li>',re.DOTALL).findall(html)
    #print match
    total = len(match)
    for link, title, year in match:
        addon.add_directory({'mode': 'tvseasons', 'url': link, 'section': 'tv', 'show': title}, {'title': title + ' (' + year + ')'}, img='', total_items=total)
    addon.end_of_directory()

def get_genres_list(url):
    print 'get_genres_list'
    html = net.http_GET(url).content
    
    match = re.compile('\t\t\t <li><a href="(.+?)\n" title="Watch .+? Online">(.+?)<span class="epnum">(.+?)</span></a></li>',re.DOTALL).findall(html)
    total = len(match)
    for link, title, year in match:
        addon.add_directory({'mode': 'tvseasons', 'url': link, 'section': 'tv', 'show': title}, {'title': title + ' (' + year + ')'}, img='', total_items=total)
    addon.end_of_directory()
        
def get_schedule_date(url):
    print 'get_schedule_list'
    html = net.http_GET(url).content
 
    match = re.compile('<li><a href="http://watchseries.eu/tvschedule/(.+?)">(.+?)</a></li>',re.DOTALL).findall(html)
    #print match
    total = len(match)
    for link, title in match:
        addon.add_directory({'mode': 'schedule_list', 'url': main_url+'/tvschedule/'+link, 'section': 'tv'}, {'title': title}, img='', total_items=total)
    addon.end_of_directory()

def get_schedule_list(url):
    print 'get_schedule_list'
    html = net.http_GET(url).content
 
    match = re.compile('\t \t\t\t\t\t\t\t\t\t\t\t\t\t <a href="(.+?)>(.+?)</a>\r\n',re.DOTALL).findall(html)
    #print match
    total = len(match)
    for link, title in match:
        #print link
        match = re.compile('(.+?)"',re.DOTALL).findall(link)[0]
        if match == '#':
            addon.add_directory({'mode': 'schedule_none', 'url': main_url+'/tvschedule/'+match, 'section': 'tv'}, {'title': title}, img='', total_items=total)
        else:
            addon.add_directory({'mode': 'tvseasons', 'url': match, 'section': 'tv', 'show': title}, {'title': title}, img='', total_items=total)
    addon.end_of_directory()

def DoSearch(searchTerm):
    print 'Searching'
    searchTerm = re.sub(' ', '%20', searchTerm)
     
    file = urllib2.urlopen('http://watchseries.eu/search/' + searchTerm)
    html = file.read()
    file.close()

    numMatches = re.search('Found (.+?) matches.', html)
    if not numMatches:  # nothing found
        addon.show_error_dialog(['Sorry, No shows found.'])
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.executebuiltin("Action(ParentDir)")
        return
    
    numMatches = int(numMatches.group(1))
    nextpage = re.search('<a href="(.+?)"> Next Search Page</a>', html)
    matches = []

    loop = True
    page = 1
    while loop or nextpage:
        loop = False
        #print 'Processing page ' + str(page)
          
        items = re.compile('<a href="(.+?)" title="watch serie.+?"><b>(.+?)</b></a>').findall(html)
        for each in items:
            matches.append(each[0]+'#####'+each[1])

        if nextpage:
            url = nextpage.group(1)
            url = re.sub(' ', '%20', url)
            print 'URL: ##' + url + '##'
            file = urllib2.urlopen(url)
            html = file.read()
            file.close()
               
            nextpage = re.search('<a href="(.+?)"> Next Search Page</a>', html)
            if not nextpage: loop = True
            page += 1
               
    for item in matches:
        parts = re.match('(.+?)#####(.+?)$', item)
        if parts:
            addon.add_directory({'mode': 'tvseasons', 'url': parts.group(1), 'section': 'tv', 'show': parts.group(2)}, {'title': parts.group(2)}, img='', total_items=numMatches)
    addon.end_of_directory()


     
     
if mode == 'main':
    print 'main' 
    addon.add_directory({'mode': 'tvaz', 'section': 'tv'}, {'title':'A-Z'}, img='')
    addon.add_directory({'mode': 'latest', 'url': main_url + '/latest', 'section': 'tv'}, {'title': 'Newest Episodes Added'})
    addon.add_directory({'mode': 'popular', 'url': main_url + '/new', 'section': 'tv'}, {'title': 'This Weeks Popular Episodes'})
    addon.add_directory({'mode': 'schedule', 'url': main_url + '/tvschedule', 'section': 'tv'}, {'title': 'TV Schedule'})
    addon.add_directory({'mode': 'genres', 'url': main_url +'/genres/', 'section': 'tv'}, {'title': 'TV Shows Genres'})
    addon.add_directory({'mode': 'search', 'section': 'tv'}, {'title':'Search'})
    addon.end_of_directory()
    
elif mode == 'tvaz':
    AZ_Menu('tvseriesaz','/letters/%s')
elif mode == 'tvseriesaz':
    get_video_list(url)
elif mode == 'latest':
    get_latest(url)
elif mode == 'popular':
    get_latest(url)
elif mode == 'schedule':
    get_schedule_date(url)
elif mode == 'schedule_list':
    get_schedule_list(url)
elif mode == 'genres':
    BrowseByGenreMenu(url)
elif mode == 'genresList':
    get_genres_list(url)
elif mode == 'search':
    keyboard = xbmc.Keyboard()
    if section == 'tv': keyboard.setHeading('Search TV Shows')
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        search_text = keyboard.getText()
        print 'SEARCH_TEXT: ' + search_text
        DoSearch(search_text)
    else:
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.executebuiltin("Action(ParentDir)")
    

elif mode == 'tvseasons':
    print 'tvseasons'
    
    sh = re.sub(' ', '%20', show)
    html = net.http_GET(url).content
    
    match = re.compile('<h2 class="lists"><a href="(.+?)">(.+?)  (.+?)</a> - ').findall(html)

    try:
        imdb_id = re.compile('<a href="http://www.imdb.com/title/(.+?)/" target="_blank">IMDB</a>', re.DOTALL).findall(html)[0]
    except:
        imdb_id = ''
        
    if addon.get_setting('usemetadata') == 'true':
        if imdb_id != '':
            arthtml = net.http_GET('http://www.thetvdb.com/api/GetSeriesByRemoteID.php?imdbid='+imdb_id).content
        else:
            arthtml = net.http_GET('http://www.thetvdb.com/api/GetSeries.php?seriesname='+sh).content

    try:
        seriesid = re.compile('<seriesid>(.+?)</seriesid>').findall(arthtml)[0]
    except:
        seriesid = ''

    seasons = re.compile('<h2 class="lists"><a href=".+?">Season ([0-9]+)  .+?</a> -').findall(html)
    num = 0
    for link, season, episodes in match:
        if not seriesid: crap = {'mode': 'tvepisodes', 'url': link, 'section': 'tvshows', 'imdb_id': imdb_id, 'season': num + 1}
        else: crap = {'mode': 'tvepisodes', 'url': link, 'section': 'tvshows', 'imdb_id': imdb_id, 'season': num + 1, 'fanart': get_FanArt(seriesid), 'seriesid': seriesid}
        if addon.get_setting('usemetadata') == 'true':
            addon.add_directory(crap, {'title': season + ' ' + episodes}, img=get_Season_Art(seriesid, str(num+1)), fanart=get_FanArt(seriesid), total_items=len(match))
        else:
            addon.add_directory(crap, {'title': season + ' ' + episodes}, img='', fanart='', total_items=len(match))
        num += 1
    addon.end_of_directory()

elif mode == 'tvepisodes':
    print 'tvepisodes'
    season = addon.queries['season']
    try:
        fa = addon.queries['fanart']
        seriesid = addon.queries['seriesid']
    except:
        fa = ''
        seriesid = ''
    
    html = net.http_GET(url).content
    match = re.compile('<li><a href="\..(.+?)"><span class="">.+?. Episode (.+?)&nbsp;(.+?)/span><span class="epnum">(.+?)</span></a>',re.DOTALL).findall(html)
    
    num = 0
    for url, episode, name, aired in match:
        if addon.get_setting('usemetadata') == 'true':
            episodeData = get_Episode_Data(seriesid, season, episode)
            if episodeData is not None:
                episodename = episodeData['name']
                firstaired = episodeData['firstaired']
                filename = episodeData['filename']
                overview = episodeData['overview']
            else:
                episodename = ''
                firstaired = ''
                filename = ''
                overview = ''
        else:
            episodename = ''
            firstaired = ''
            filename = ''
            overview = ''
        
        print 'EPISODE NAME: ' + episodename
        print 'FIRST AIRED: ' + firstaired    
        print 'FILENAME: ' + filename    
        print 'OVERVIEW: ' + overview
        #print 'ARTHTML: ' + arthtml
        
        if episodename == '':
            try:
                name1 = re.compile('&nbsp;&nbsp;(.+?)<',re.DOTALL).findall(name)[0]
            except: 
                name1 = ' '
            episodename = name1
            firstaired = aired
            
        if addon.get_setting('usemetadata') == 'true':
            addon.add_directory({'mode': 'hosting_sites', 'url': main_url + url, 'section': 'tvshows', 'imdb_id': imdb_id, 'episode': num + 1, 'fanart': fa, 'episodeart': filename} ,{'title':episode+' '+episodename+' ('+firstaired+')', 'plot': overview}, img=filename, fanart=fa, total_items=len(match))
        else:
            addon.add_directory({'mode': 'hosting_sites', 'url': main_url + url, 'section': 'tvshows', 'imdb_id': imdb_id, 'episode': num + 1}, {'title':episode+' '+episodename+' ('+firstaired+')'}, img='', total_items=len(match))
    addon.end_of_directory()

elif mode == 'hosting_sites':
    try:
        # Get the episode id from the url
        match = re.compile('-(.+?).html').findall(url)[0]
        # load the main url so the cookie gets set properly. Otherwise we will not resolve properly
        html = net.http_GET(url).content
        net.save_cookies(profile_path+'cookie.txt')
        # Fetch the links
        html = net.http_GET(main_url+'/getlinks.php?q='+match+'&domain=all').content
    except urllib2.URLError, e:
        html = ''

    try:
        fa = addon.queries['fanart']
        filename = addon.queries['episodeart']
    except:
        fa = ''
        filename = ''
    
    hosts = re.finditer('<div class="site">\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t(.+?)\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t</div>\r\n\t\t\t\t\t\t\t\t\t\t\t\t<div class="siteparts">\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t<a href="..(.+?)" target="_blank".+?class="user">(.+?)</div>', html, re.DOTALL)
                         
    sources = []

    num = 0
    for s in hosts:
        #print s.groups()
        title, url, percent = s.groups()
        
        if urlresolver.HostedMediaFile(host=title, media_id='xxx'):
            num += 1
            sources.append([title, url, percent])

    if num == 0:
        addon.show_error_dialog(['Sorry, No hosts found.'])
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.executebuiltin("Action(ParentDir)")
    #elif num == 1:      # only one host available. Play it...
    #    command = 'RunScript(plugin.video.watchseries.eu,%s,?mode=play&url=%s&section=tvshows)' %(sys.argv[1], main_url+url)
    #    xbmc.executebuiltin(command)
    #    xbmc.executebuiltin("Action(ParentDir)")
    #    addon.end_of_directory()
    else:
        for s in sources:
            title = s[0]
            url = s[1]
            percent = s[2]
           
            if addon.get_setting('showpercent') == 'true': outtitle = title + ' - ' + percent
            else: outtitle = title
            if addon.get_setting('usemetadata') == 'true':
                addon.add_directory({'mode': 'play', 'url': main_url+url, 'section': 'tvshows'} ,{'title':outtitle}, img=filename, fanart=fa)
            else:
                addon.add_directory({'mode': 'play', 'url': main_url+url, 'section': 'tvshows'} , {'title':outtitle})
        addon.end_of_directory()

        
            
elif mode == 'play':
    url = addon.queries['url']
    net.set_cookies(profile_path+'cookie.txt')
    html = net.http_GET(url).content
    match = re.compile('\r\n\t\t\t\t<a href="(.+?)" class="myButton">').findall(html)[0]
    print 'match'
    print match
    post_url = net.http_GET(match).get_url()
    print 'post url'
    print post_url
    
    try:
        error = re.compile('404').findall(post_url)[0]
    except:
        error = ''
        
    if error != '':
        addon.show_error_dialog(['Sorry, File has been deleted from host.', 'Try another host.'])
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.executebuiltin("Action(ParentDir)")
    else:
        stream_url = urlresolver.HostedMediaFile(post_url).resolve()
        print stream_url
        ok=xbmc.Player(xbmc.PLAYER_CORE_DVDPLAYER).play(stream_url)
        addon.add_directory({'mode': 'play', 'url': url, 'section': 'tv'}, {'title': 'Play Again'})
        addon.end_of_directory()
        
elif mode == 'resolver_settings':
    urlresolver.display_settings()

if not play:
    addon.end_of_directory()
    
