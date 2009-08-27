from settings import USER, PASS # For testing purposes

LOGIN_URL = "https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral"
MARK_READ_URL = "https://www.google.com/voice/m/mark?read=1&id="
SMSLIST_URL = "https://www.google.com/voice/inbox/recent/sms" # We use the main website because Google includes helpful data stored via JSON here
SMSLIST_M_URL = "https://www.google.com/voice/m/i/sms"
SMS_SEND_URL = "https://www.google.com/voice/m/sendsms"

from re import compile
timeConstrain = compile("now|\d{1,2} (seconds?|minutes?) ago|(1?\d|2[0-4]) hours? ago")

# Todo: Add multiple pages of messages support

class GVAccount:
    """A representation of the user to handle their login, cookies, and message sending and receiving."""
    def __init__(self, username, password):
        self.last_time = 0 # A failsafe in case no other message can set the baseline.
        self.uid = None # Google has a special little id that they require is included in sending messages
        self.logged_in = False
        self.initialized = False
        print "Logging in..."
        self.login(username, password)
    
    def __markRead(self, conversation_ids):
        # Each conversation has its own id, so we can pass that via GET to mark it as read.
        """ Takes a list of conversation ids and makes GET requests to Google's
        httpd to mark them as read conversations."""
        for cid in conversation_ids:
            from urllib2 import Request, urlopen
            print "Marking %s as read" % cid
            urlopen(Request(MARK_READ_URL + cid))
    
    def __smsParse(self, sms_page):
        """Parses the HTML received from Google's servers to receive only the relevant messages."""
        from lxml import etree, html
        parser = etree.XMLParser(strip_cdata=False) # Google likes to store their information in CDATA, so we have to tell the parser this
        parsed_html = html.document_fromstring(sms_page.read(), parser)
        message_ids = {}
        import cjson
        json = cjson.decode(parsed_html.find('.json').text)
        # We only want to get relevant conversations
        for key, value in json['messages'].iteritems():
            # Check if unread and within the past twenty-four hours
            from time import time
            # Google's precision goes to the thousandths
            value['startTime'] = float(value['startTime'])/1000
            # Checks for multiple things:
            #   - Message is a SMS in the inbox
            #   - Message is unread
            #   - Message is within the past 24 hours
            if not value['isRead'] and (time() - value['startTime'] < 86400) and ('sms' in value['labels']) and ('inbox' in value['labels']):
                # If not initialized, then the -very- last message sent is
                # found. This is used when later detecting new messages.
                if int(value['startTime']) > self.last_time:
                    self.last_time = value['startTime']
                    if self.initialized:
                        if key not in message_ids:
                            pass # Should not need to do anything if id already indexed
                        else:
                            # Later switch to tuple to store phone number and conversation notes?
                            message_ids[key] = value['phoneNumber']
                        print "Message ID: %s" % key
        if not self.initialized: self.initialized = True
        return message_ids
    
    def login(self, username, password):
        """Logs into the Google Account system and receives the cookies into a
        file to allow continued use of the Google Voice system."""
        if not self.logged_in:# We don't need to repeat this process over and over
            from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
            from cookielib import LWPCookieJar
            # Switch to UUID instead, then default to user if an older version of the python
            cookie_jar = LWPCookieJar("%s.lwp" % username) # Named using the username to prevent overlap with another user.
            opener = build_opener(HTTPCookieProcessor(cookie_jar))
            install_opener(opener) # Let Google know we'll accept its nomtastic cookies
            from urllib import urlencode
            form = urlencode({ # Will be pushed to Google via POST
                'continue': 'https://www.google.com/voice/m/i/sms/',
                'Email': username,
                'Passwd': password,
                'PersistentCookies': 'yes',
            })
            urlopen(Request(LOGIN_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))
            self.logged_in = True
            self.__find_account_id()
    
    def __find_account_id(self):
        if self.uid is None:
            from urllib2 import Request, urlopen
            handle = urlopen(Request(SMSLIST_M_URL))
            from lxml import html
            parsed_html = html.fromstring(handle.read())
            # Grab UID from the page and set it.
            self.uid = parsed_html.forms[0].inputs["_rnr_se"].value
    
    def sms_check(self):
        """Retrieves the SMS messages from Google's servers to pass to the Parse function."""
        from urllib2 import Request, urlopen
        handle = urlopen(Request(SMSLIST_URL))
        self.__markRead(self.__smsParse(handle))
    
    def sms_send(self, number, message):
        from urllib2 import Request, urlopen
        from urllib import urlencode
        form = urlencode({
            'number': number,
            'smstext': message,
            '_rnr_se': self.uid,
        })
        urlopen(Request(SMS_SEND_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))

# Also for testing purposes
x = GVAccount(USER, PASS)
# from lxml import html
# z = x.sms_check()
