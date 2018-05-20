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

class Page(ndb.Model):
    last_scraped = ndb.DateTimeProperty()

class Scrape(ndb.Model):
    content = ndb.TextProperty()
    scraped_on = ndb.DateTimeProperty()

class Diff(ndb.Model):
    title = ndb.TextProperty()
    content = ndb.TextProperty()
    diffed_on = ndb.DateTimeProperty()

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
    
    
def fetch(url):
    r = urlfetch.fetch(url)
    if r.status_code != 200:
        return False
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
    stripper = HtmlStripper(base=url)
    stripper.feed(content)
    content = stripper.content
    return content.encode('utf-8')

def get_last_scrape(url):
    page_key = ndb.Key('Page',url)
    page = page_key.get()
    if page:
        last_scrape_key = ndb.Key('Page',url,'Scrape',str(page.last_scraped))
        last_scrape = last_scrape_key.get()
        if last_scrape:
            return last_scrape
    return None

            
def maybe_create_diff(url):
    now = datetime.now()
    last_scrape = get_last_scrape(url)
    if last_scrape and now - last_scrape.scraped_on < timedelta(seconds=1):
        return False
    new_content = fetch(url)
    if not new_content:
        return False
    if last_scrape and new_content == last_scrape.content:
        return False

    page_key = ndb.Key('Page',url)
    page = page_key.get()
    if not page:
        page = Page(id=url)
    page.last_scraped = now
    page.put()
    
    scrape = Scrape(id=str(now),parent=page_key)
    scrape.content = new_content
    scrape.scraped_on = now
    scrape.put()

    diff = Diff(parent=page_key)
    if last_scrape:
        diff.title = 'New content on %s between %s and %s'%(url,last_scrape.scraped_on,now)
        diff.content = '<h4>%s:</h4>'%diff.title
        indiff=False
        for line in difflib.ndiff(last_scrape.content.split('\n'),
                                  new_content.split('\n')):
            if line[0]=='+':
                if not indiff:
                    diff.content += '<div style="margin:1em; border: thin solid black">'
                diff.content += line[1:]
                indiff=True
            else:
                if indiff:
                    diff.content += '</div>'
                    indiff=False
    else:
        diff.title = 'First Scrape of %s (on %s)'%(url,now)
        diff.content = '<h4>%s:</h4>'%diff.title
        diff.content += '<div style="white-space:pre-line">'
        diff.content += new_content
        diff.content += '</div>'

    diff.diffed_on = now
    diff.put()

    return True

class Feed(webapp2.RequestHandler):
    def get(self):
        url = self.request.get('url')
        maybe_create_diff(url)
        page_key = ndb.Key('Page',url)
        diffs = Diff.query(ancestor=page_key).order(-Diff.diffed_on)
        fg=FeedGenerator()
        fg.title('Changes to %s' % url)
        fg.link(href='http://page2rss-174917.appspot.com/feed?%s'%url)
        fg.description('Changes to %s' % url)
        n=0
        for diff in diffs:
            if n<5:
                fe = fg.add_entry()
                fe.title(diff.title)
                fe.link(href=url)
                fe.pubdate(diff.diffed_on.replace(tzinfo=utc))
                fe.content(diff.content)
            else:
                diff.key.delete()
            n+=1
        self.response.headers['Content-Type'] = 'application/rss+xml'
        self.response.write(fg.rss_str(pretty=True))
        

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/feed',Feed)
], debug=True)
