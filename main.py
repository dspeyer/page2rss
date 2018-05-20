import webapp2
from feedgen.feed import FeedGenerator
from datetime import datetime, tzinfo, timedelta
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
import re
import difflib
from HTMLParser import HTMLParser

#from pytz import utc

ZERO = timedelta(0)
class UTC(tzinfo):
    """UTC"""
    def utcoffset(self, dt):
        return ZERO
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return ZERO
utc = UTC()

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Hello, World!')

class TestFeed(webapp2.RequestHandler):
    def get(self):
        n = int(self.request.get('n','4'))
        fg=FeedGenerator()
        fg.title('Test RSS Feed')
        fg.link(href='http://page2rss-174917.appspot.com/')
        fg.description('Had this been an actual RSS feed...')
        for i in range(5):
            fe = fg.add_entry()
            fe.title('Test entry %d' % (i+n))
            fe.link(href='http://page2rss-174917.appspot.com/%d' % i)
            fe.pubdate(datetime(2017,i+1,4,tzinfo=utc))
            fe.content('''<div>
This is some descriptive text.

This is a rough paragraph.  Very rough.

<p>This is an HTML paragraph.  The "number" %d is <b>The Best</b></p></div>''' % (i+n),
                       type='CDATA')
        self.response.headers['Content-Type'] = 'application/rss+xml'
        self.response.write(fg.rss_str(pretty=True))


class Page(ndb.Model):
    last_scraped = ndb.DateTimeProperty()

class Scrape(ndb.Model):
    content = ndb.TextProperty()
    scraped_on = ndb.DateTimeProperty()

def getlink(lis,key,base):
    for (k,v) in lis:
        if k==key:
            if '//' in v:
                return v
            else:
                return base+'/'+v
    return None
    
class HtmlStripper(HTMLParser):
    def __init__(self, base):
        HTMLParser.__init__(self)
        self.content = ''
        self.inlink = False
        self.silent = False
        self.base = base
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            self.content += '<a href="%s">'%getlink(attrs,'href',self.base)
            self.inlink = True
        if tag=='img':
            self.content += '<img src="%s">'%getlink(attrs,'src',self.base)
            if not self.inlink:
                self.content += '\n'
        if tag in ['script','style']:
            self.silent = True
    def handle_endtag(self, tag):
        if tag=='a' and self.inlink:
            self.content += '</a>\n'
        if tag in ['script','style']:
            self.silent = False
    def handle_data(self,data):
        if not self.silent:
            self.content += data
            if not self.inlink:
                self.content += '\n'
    
    
def scrape(url):
    now = datetime.now()
    page_key = ndb.Key('Page',url)
    page = page_key.get()
    last_scrape_content = None
    if page:
        if now - page.last_scraped < timedelta(seconds=1):
            return (False, -1)
        last_scrape_key = ndb.Key('Page',url,'Scrape',str(page.last_scraped))
        last_scrape = last_scrape_key.get()
        if last_scrape:
            last_scrape_content = last_scrape_key.get().content
    else:
        page = Page(id=url)
    r = urlfetch.fetch(url)
    if r.status_code != 200:
        return (False, r.status_code)
    try:
        content = r.content.decode('ascii')
    except UnicodeDecodeError:
        try:
            content = r.content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                content = r.content.decode('latin-1')
            except UnicodeDecodeError:
                content = re.sub(r'[^\x00-\x7F]+',' ', r.content)
    parser = HtmlStripper(base=url)
    parser.feed(content)
    content = parser.content
    page.last_scraped = now
    scrape = Scrape(id=str(now),parent=page_key)
    scrape.content = content.encode('utf-8')
    scrape.scraped_on = now
    scrape.put()
    page.put()
    return (last_scrape_content, content)
    
class Diff(webapp2.RequestHandler):
    def get(self):
        url = self.request.get('url')
        (lc,nc) = scrape(url)
        if lc==False:
            self.response.write('<h2>Error %d</h2>'%nc)
        elif lc==None:
            self.response.write('<h3>All New Content:</h3><hr><pre>%s</pre>'%nc)
        else:
            d = difflib.ndiff(lc.split('\n'),nc.split('\n'))
            self.response.write('<h2>Changes:</h2>')
            indiff = False
            for line in d:
                if line[0]=='+':
                    if not indiff:
                        self.response.write('<abbr style="display: block; border: thin solid black">')
                    self.response.write(line[1:])
                    indiff=True
                else:
                    if indiff:
                        self.response.write('</abbr>')
                        indiff=False
            

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/test.rss', TestFeed),
    ('/diff',Diff)
], debug=True)
