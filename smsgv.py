from settings import USER, PASS # For testing purposes

LOGIN_URL = "https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral"
MARK_READ_URL = "https://www.google.com/voice/m/mark?read=1&id="
SMSLIST_URL = "https://www.google.com/voice/inbox/recent/sms" # We use the main website because Google includes helpful data stored via JSON here
# SMSLIST_URL = "https://www.google.com/voice/m/i/sms"
SMSSEND_URL = "https://www.google.com/voice/m/sendsms"

from re import compile
timeConstrain = compile("now|\d{1,2} (seconds?|minutes?) ago|(1?\d|2[0-4]) hours? ago")

# Todo: Add multiple pages of messages support

class GVAccount:
    """A representation of the user to handle their login, cookies, and message sending and receiving."""
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.last_time = 0 # A failsafe in case no other message can set the baseline.
        self.uid = None # Google has a special little id that they require is included in sending messages
        self.loggedIn = False
        self.initialized = False
        print "Logging in..."
        self.login()
        # print "Making initial SMS check..."
        # self.smsCheck()
    
    # Potentially needs removal
    def __convertTime(self, time):
        """Converts the time format produced by Google to a HHMM 24-hour style for comparisons."""
        # Format of the original time: x?x:xx (A|P)M
        time = time.split(':') # yields ('x?x', 'xx (A|P)M')
        newTime = ""
        # Set the hours to a 24-hour format
        if time[1].split(' ')[1] == "PM": newTime = str(int(time[0]) + 12)
        else: newTime = "%.2d" % int(time[0])
        newTime += time[1].split(' ')[0] # minutes
        return newTime
    
    def __markRead(self, conversation_ids):
        # Each conversation has its own id, so we can pass that via GET to mark it as read.
        """ Takes a list of conversation ids and makes GET requests to Google's
        httpd to mark them as read conversations."""
        for cid in conversation_ids:
            from urllib2 import Request, urlopen
            print "Marking %s as read" % cid
            urlopen(Request(MARK_READ_URL + cid))
    
    # Potentially needs removal
    def __uplevel(self, tree, levels):
        """Given the nature of having to traverse the DOM, this function will
        serve to shorten the rest of the code from repetitive getparent() calls."""
        if levels == 1: return tree.getparent()
        else: return self.__uplevel(tree.getparent(), levels-1)
    
    def __smsParse(self, sms_page):
        """Parses the HTML received from Google's servers to receive only the relevant messages."""
        from lxml import etree, html
        parser = etree.XMLParser(strip_cdata=False) # Google likes to store their information in CDATA, so we have to tell the parser this
        parsed_html = html.document_fromstring(sms_page.read(), parser)
        message_ids = set()
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
                        message_ids.add(key)
                        print value
                        print "Message ID: %s" % key
        if not self.initialized: self.initialized = True
        return message_ids
        
        # from lxml import html
        # parsed_html = html.fromstring(sms_page.read())
        # if self.uid is None: self.uid = parsed_html.forms[0].inputs["_rnr_se"].value
        # message_ids = set() # sets allow for unique data, we don't need to request something for a conversation more than once
        # 
        # # We're only looking for new messages
        # for unread_message in parsed_html.find_class("ms3"): # Class denotes a message object within a conversation
        #     message_parent = unread_message.getparent()
        #     if message_parent.get("class") == "mu": # Class denotes an unread message
        #         for timestamp in message_parent.find_class("ms"):
        #             if timestamp.getparent().get("class") is None and timeConstrain.match(timestamp.text.strip(" ()")):
        #                 for piece in unread_message.find_class("ms"): # Class denotes a timestamp
        #                     time = self.__convertTime(piece.text.strip(" ()"))
        #                     if self.initialized:
        #                         for sender in piece.getprevious().getprevious().find_class("sf"): # Class denotes the sender field
        #                             sender = sender.text_content().strip(' \n').strip(' ')
        #                             # We only want the sender's messages and we want it to make sure it has not been previously retrieved
        #                             if sender == "Me:" or int(time) <= int(self.lastTime):
        #                                 break
        #                             else:
        #                                 # The first time through, we do not desire to parse messages, but to find a time base for which to determine whether or not a new message should be sent.
        #                                 print "%s %s %s (%s)" % (sender, piece.getprevious().text, piece.text.strip(" ()"), (self.lastTime)) #self.__uplevel(piece, 3).get("id"))
        #                                 message_ids.add(self.__uplevel(piece, 3).get("id"))
        #                     if piece.getparent().getnext().getnext() is None and self.__uplevel(piece, 3).getprevious().getprevious().getprevious() is None and (int(time) > int(self.lastTime)): # Sorry for it being messy, but we only want to use the latest message as a time baseline.
        #                         # This appears to be the latest message (at least from the conversation), so we will use it as the basis for checking for new text messages
        #                         self.lastTime = time
        # if not self.initialized: self.initialized = True
        # return message_ids # returns set of ids that were parsed
    
    def login(self):
        """Logs into the Google Account system and receives the cookies into a
        file to allow continued use of the Google Voice system."""
        if not self.loggedIn:# We don't need to repeat this process over and over
            from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
            from cookielib import LWPCookieJar
            # Switch to UUID instead, then default to user if an older version of the python
            cookie_jar = LWPCookieJar("%s.lwp" % self.username) # Named using the username to prevent overlap with another user.
            opener = build_opener(HTTPCookieProcessor(cookie_jar))
            install_opener(opener) # Let Google know we'll accept its nomtastic cookies
            from urllib import urlencode
            form = urlencode({ # Will be pushed to Google via POST
                'continue': 'https://www.google.com/voice/m/i/sms/',
                'Email': self.username,
                'Passwd': self.password,
                'PersistentCookies': 'yes',
            })
            urlopen(Request(LOGIN_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))
            self.loggedIn = Trues
    
    def smsCheck(self):
        """Retrieves the SMS messages from Google's servers to pass to the Parse function."""
        from urllib2 import Request, urlopen
        handle = urlopen(Request(SMSLIST_URL))
        self.__markRead(self.__smsParse(handle))
    
    def smsSend(self, number, message):
        from urllib2 import Request, urlopen
        from urllib import urlencode
        form = urlencode({
            'number': number,
            'smstext': message,
            '_rnr_se': self.uid,
            # IMPORTANT! We MUST get this self.uid from somewhere, probably the mobile site.
            # if self.uid is None: self.uid = parsed_html.forms[0].inputs["_rnr_se"].value
        })
        urlopen(Request(SMSSEND_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))

# Also for testing purposes
x = GVAccount(USER, PASS)
from lxml import html
z = x.smsCheck()