import webapp2
from feedgen.feed import FeedGenerator
from datetime import datetime, tzinfo, timedelta
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
        fg=FeedGenerator()
        fg.title('Test RSS Feed')
        fg.link(href='http://page2rss-174917.appspot.com/')
        fg.description('Had this been an actual RSS feed...')
        for i in range(4):
            fe = fg.add_entry()
            fe.title('Test entry %d' % i)
            fe.link(href='http://page2rss-174917.appspot.com/%d' % i)
            fe.pubdate(datetime(2017,i+1,4,tzinfo=utc))
        self.response.headers['Content-Type'] = 'application/rss+xml'
        self.response.write(fg.rss_str(pretty=True))
            
app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/test.rss', TestFeed)
], debug=True)
