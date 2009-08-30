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
        if type(self.time) is str:
            from time import strptime
            self.time = self.time.strip()
            self.time = strptime(self.time, '%I:%M %p')
    
    def __str__(self):
        from time import strftime
        return '%s\t%s' % (strftime('%H:%M', self.time), self.message)

class GVAccount:
    """A representation of the user to handle their login, cookies, and message sending and receiving."""
    def __init__(self, username, password):
        self.last_time      = 0 # A failsafe in case no other message can set the baseline.
        self.temp_time      = 0
        self.logged_in      = False
        self.initialized    = False
        self.conversations  = {}
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
    
    def __id_gather(self, parsed_html):
        """Parses the HTML received from Google's servers to receive only the relevant messages."""
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
            if (time() - value['startTime'] < 86400) and ('sms' in value['labels']) and ('inbox' in value['labels']):
                # If not initialized, then the -very- last message sent is
                # found. This is used when later detecting new messages.
                if int(value['startTime']) > self.last_time:
                    self.temp_time = value['startTime'] # Error here?
                    if key in self.conversations:
                        self.conversations[key] = [self.conversations[key][0], False, []]
                    else:
                        if not self.initialized:
                            self.conversations[key] = [None, False, []] # (last_hash, first time?, [Message, Message])
                        else:
                            self.conversations[key] = [None, True, []] # (last_hash, first time?, [Message, Message])
        if self.temp_time == 0:
            self.temp_time = self.last_time
        if not self.initialized:
            self.initialized = True
        return None # TODO: Change to return a dictionary or list/tuple of data rather than just the message ID. [Time? Return phone #.]
    
    def __sms_parse(self, sms_page):
        from lxml import etree, html
        # Strip CDATA tags
        html_page = sms_page.read()
        html_page = html_page.replace('<![CDATA[', '')
        html_page = html_page.replace(']]>', '')
        parsed_html = html.document_fromstring(html_page)
        self.__id_gather(parsed_html) # Also sets initialized to true if necessary
        for cid in self.conversations.iterkeys():
            # Traverses down the DOM to get to the proper div that contains all of the SMS data
            # The -1 brings us to the end to retrieve the very last message.
            try:
                conversation = parsed_html.find_class('gc-message')[0].getparent().get_element_by_id(cid).find_class('gc-message-message-display')[-1]
            except KeyError:
                del self.conversations[cid]
            else:
                from time import strftime, localtime
                message_count = len(conversation) - 1
                if len(conversation) > 2 and conversation[2].get('class') == 'gc-message-sms-old':
                    message_count += len(conversation[2]) - 1
                    message_count =  [0, 1, range(message_count-3), 4]
                else:
                    message_count = range(message_count+1)
                found_unread = False
                # Error with getting first message of a new conversation
                # and with a KeyError when a conversation no longer exists
                # (use try...except block)
                while not found_unread:
                    for mid in message_count:
                        if self.conversations[cid][0] == None:
                            message = conversation[-1]
                            message = hash('%s %s' % (message[2].text, message[1].text)) # hash('time message')
                            self.conversations[cid][0] = message
                        if found_unread == False:
                            if type(mid) is type([]):
                                for second_mid in mid:
                                    if found_unread == False:
                                        message = conversation[2][-(second_mid+1)]
                                        message_hash = hash('%s %s' % (message[2].text, message[1].text)) # hash('time message')
                                        if self.conversations[cid][0] == message_hash:
                                            found_unread = True
                                            if self.conversations[cid][1]:
                                                message = GVSMS(message[2].text, message[1].text)
                                                self.conversations[cid][2].append(message)
                                        else:
                                            message = GVSMS(message[2].text, message[1].text)
                                            self.conversations[cid][2].append(message)
                            else:
                                message = conversation[-(mid+1)]
                                message_hash = hash('%s %s' % (message[2].text, message[1].text)) # hash('time message')
                                if self.conversations[cid][0] == message_hash:
                                    found_unread = True
                                    if self.conversations[cid][1]:
                                        message = GVSMS(message[2].text, message[1].text)
                                        self.conversations[cid][2].append(message)
                                else:
                                    message = GVSMS(message[2].text, message[1].text)
                                    self.conversations[cid][2].append(message)
                        else:
                            break
            try:
                message = conversation[-1]
                message = hash('%s %s' % (message[2].text, message[1].text)) # hash('time message')
                self.conversations[cid][0] = message
            except:
                pass
            # The above substrings are simply for proper formatting right now.
        self.last_time = self.temp_time
        return None
    
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
        self.__sms_parse(handle)
        for cid, cdata in self.conversations.iteritems():
            cdata = cdata[2]
            for index in range(len(cdata)):
                print cdata.pop()
        return None
    
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
