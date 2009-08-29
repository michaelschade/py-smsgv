from settings import USER, PASS # For testing purposes

# We use the mobile website for everything possible to save on bandwidth
LOGIN_URL       = 'https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral'
SMS_SEND_URL    = 'https://www.google.com/voice/m/sendsms'
MARK_READ_URL   = 'https://www.google.com/voice/m/mark?read=1&id='
SMSLIST_M_URL   = 'https://www.google.com/voice/m/i/sms'
# We use the main website (instead of mobile) because Google includes helpful data stored via JSON here
SMSLIST_URL     = 'https://www.google.com/voice/inbox/recent/sms'

# Todo: Add multiple pages of messages support

class GVSMS:
    def __init__(self, time, message):
        self.time       = time
        self.message    = message
    
    def __str__(self):
        return '%s\t%s' % (self.time, self.message)

class GVAccount:
    """A representation of the user to handle their login, cookies, and message sending and receiving."""
    def __init__(self, username, password):
        self.last_time = 0 # A failsafe in case no other message can set the baseline.
        self.temp_time = 0
        self.logged_in = False
        self.initialized = False
        print "Logging in..."
        self.login(username, password)
    
    def __mark_read(self, conversation_id):
        # Each conversation has its own id, so we can pass that via GET to mark it as read.
        """makes GET requests to Google's httpd to mark conversation as read."""
        from urllib2 import Request, urlopen
        print "Marking %s as read" % conversation_id
        urlopen(Request(MARK_READ_URL + conversation_id))
    
    def __find_account_id(self):
        """Finds account ID used by Google to authenticate SMS sending."""
        # Google has a special little id that they require is included in sending messages
        from urllib2 import Request, urlopen
        handle = urlopen(Request(SMSLIST_M_URL))
        from lxml import html
        parsed_html = html.fromstring(handle.read())
        # Grab UID from the page and set it.
        self.uid = parsed_html.forms[0].inputs["_rnr_se"].value
    
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
    
    def __id_gather(self, parsed_html):
        """Parses the HTML received from Google's servers to receive only the relevant messages."""
        conversations = {}
        import cjson
        json = cjson.decode(parsed_html.find('.//json').text)
        # We only want to get relevant conversations
        for key, value in json['messages'].iteritems():
            # Check if unread and within the past twenty-four hours
            from time import time
            # Google's precision goes to the thousandths
            value['startTime'] = float(value['startTime'])/1000
            # Checks for multiple things:
            #   - Message is a SMS in the inbox
            #   - Message is unread
            #   - Message is within the past 24 hours (86,400 seconds)
            if not value['isRead'] and (time() - value['startTime'] < 86400) and ('sms' in value['labels']) and ('inbox' in value['labels']):
                # If not initialized, then the -very- last message sent is
                # found. This is used when later detecting new messages.
                if int(value['startTime']) > self.last_time:
                    self.temp_time = value['startTime'] # Error here?
                    if not self.initialized:
                        conversations[key] = [None, []] # (last_hash, [Message, Message])
        if self.temp_time == 0:
            self.temp_time = self.last_time
        if not self.initialized: self.initialized = True
        return conversations # TODO: Change to return a dictionary or list/tuple of data rather than just the message ID. [Time? Return phone #.]
    
    def __sms_parse(self, sms_page):
        from lxml import etree, html
        # Strip CDATA tags
        html_page = sms_page.read()
        html_page = html_page.replace('<![CDATA[', '')
        html_page = html_page.replace(']]>', '')
        parsed_html = html.document_fromstring(html_page)
        conversations = self.__id_gather(parsed_html) # Also sets initialized to true if necessary
        for cid in conversations.iterkeys():
            # Traverses down the DOM to get to the proper div that contains all of the SMS data
            # The -1 brings us to the end to retrieve the very last message,
            conversation = parsed_html.find_class('gc-message-sms')[0].getparent().get_element_by_id(cid).find_class('gc-message-message-display')[-1] # [-1][-1] to select very LAST message
            from time import strftime, localtime
            # print int(strftime('%H%M',   mlocaltime(self.last_time)))
            # print int(self.__convertTime(conversation[-5][2].text[1:]))
            message_count = len(conversation) - 1
            if len(conversation) > 2 and conversation[2].get('class') == 'gc-message-sms-old':
                message_count += len(conversation[2]) - 1
                message_count =  [0, 1, range(message_count-3), 4]
            else:
                message_count = range(message_count+1)
            for mid in message_count:
                if type(mid) is type([]):
                    for second_mid in mid:
                        message = conversation[2][-(second_mid+1)]
                        message = GVSMS(message[2].text, message[1].text)
                        conversations[cid][1].append(message)
                else:
                    message = conversation[-(mid+1)]
                    message = GVSMS(message[2].text, message[1].text)
                    conversations[cid][1].append(message)
            message = conversation[-1]
            message = hash('%s %s' % (message[2].text, message[1].text)) # hash('time message')
            conversations[cid][0] = message
            # The above substrings are simply for proper formatting right now.
        self.last_time = self.temp_time
        return conversations
    
    def login(self, username, password):
        """Logs into the Google Account system and receives the cookies into a
        file to allow continued use of the Google Voice system."""
        if not self.logged_in:# We don't need to repeat this process over and over
            from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
            from cookielib import LWPCookieJar
            # Switch to UUID instead, then default to user if an older version of the python
            cookie_jar = LWPCookieJar("%s.lwp" % username) # Named using the username to prevent overlap with another user.
            # TODO: Evaluate possibility of cookie_jar.save() and .load() to add failsafe in case of need to 'relogin'
            opener = build_opener(HTTPCookieProcessor(cookie_jar))
            install_opener(opener) # Let Google know we'll accept its nomtastic cookies
            from urllib import urlencode
            form = urlencode({ # Will be pushed to Google via POST
                'continue': SMSLIST_M_URL,
                'Email': username,
                'Passwd': password,
                'PersistentCookies': 'yes',
            })
            urlopen(Request(LOGIN_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))
            self.logged_in = True
            self.__find_account_id()
    
    def sms_check(self):
        """Retrieves the SMS messages from Google's servers to pass to the Parse function."""
        from urllib2 import Request, urlopen
        handle = urlopen(Request(SMSLIST_URL))
        conversations = self.__sms_parse(handle)
        for cid in conversations.iterkeys():
            self.__mark_read(cid)
        for cid, cdata in conversations.iteritems():
            cdata = cdata[1]
            for index in range(len(cdata)):
                print cdata.pop()
        return conversations
    
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
gv = GVAccount(USER, PASS)
x = gv.sms_check()
