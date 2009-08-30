# We use the mobile website for everything possible to save on bandwidth
LOGIN_URL       = 'https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral'
SEND_SMS_URL    = 'https://www.google.com/voice/m/sendsms'
READ_URL        = 'https://www.google.com/voice/m/mark?read=1&id='
UNREAD_URL      = 'https://www.google.com/voice/m/mark?read=0&id='
SMSLIST_M_URL   = 'https://www.google.com/voice/m/i/sms'
ARCHIVE_URL     = 'https://www.google.com/voice/m/archive?id='
# We use the main website (instead of mobile) because Google includes helpful data stored via JSON here
SMSLIST_URL     = 'https://www.google.com/voice/inbox/recent/sms'

# Todo: Add multiple pages of messages support

class NotLoggedIn(Exception):
    def __init__(self, username):
        self.username = str(username)
    def __str__(self):
        return self.username

class GVAccount:
    """Handles account-related functions of Google Voice for smsGV."""
    def __init__(self, username, password):
        self.id             = None
        self.username       = str(username)
        from cookielib import LWPCookieJar
        self.cookies        = LWPCookieJar("%s.lwp" % self.username) # Named using the username to prevent overlap with another user.
        # Switch to UUID instead, then default to user if an older version of the python
        # TODO: Evaluate possibility of cookie_jar.save() and .load() to add failsafe in case of need to 'relogin'
        self.logged_in      = False
        self.last_time      = 0
        self.initialized    = False
        self.conversations  = {}
        self.login(password)
    
    def __str__(self):
        return '%s' % self.username
    
    def __find_id               (self):
        """Finds account ID used by Google to authenticate SMS sending."""
        # Google has a special little id that they require is included in sending messages
        from urllib2 import Request, urlopen
        handle = urlopen(Request(SMSLIST_M_URL))
        from lxml import html
        parsed_html = html.fromstring(handle.read())
        # Grab UID from the page and set it.
        self.id = parsed_html.forms[0].inputs["_rnr_se"].value
    
    def login                   (self, password):
        """Logs into the Google Account system and receives the cookies into a
        file to allow continued use of the Google Voice system."""
        if not self.logged_in:# We don't need to repeat this process over and over
            from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
            opener = build_opener(HTTPCookieProcessor(self.cookies))
            install_opener(opener) # Let Google know we'll accept its nomtastic cookies
            from urllib import urlencode
            form = urlencode({ # Will be pushed to Google via POST
                'continue': SMSLIST_M_URL,
                'Email': self.username,
                'Passwd': password,
                'PersistentCookies': 'yes',
            })
            urlopen(Request(LOGIN_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))
            self.logged_in = True
            self.__find_id()
        self.check_sms()    # Initialization check
        if not self.initialized:
            self.initialized = True
    
    def logout                  (self):
        """Unsets all cookies and resets variables with semi-sensitive data."""
        self.cookies.clear()
        self.id             = None
        self.initialized    = False
        self.logged_in      = False
        self.conversations  = {}
    
    def send_sms                (self, number, message):
        if self.logged_in:
            from urllib2 import Request, urlopen
            from urllib import urlencode
            form = urlencode({
                'number': number,
                'smstext': message,
                '_rnr_se': self.id,
            })
            urlopen(Request(SEND_SMS_URL, form, {'Content-type': 'application/x-www-form-urlencoded'}))
        else:
            raise NotLoggedIn(self.username)
    
    def __find_conversations    (self, sms_list):
        """Parses the HTML received from Google's servers to receive only the relevant messages."""
        import cjson
        json = cjson.decode(sms_list.find('.//json').text)
        # We only want to get relevant conversations
        for conversation_data in json['messages'].itervalues():
            # Check if unread and within the past twenty-four hours
            from time import time
            # Google's precision goes to the thousandths
            conversation_data['startTime'] = float(conversation_data['startTime'])/1000
            # Checks for multiple things:
            #   - Message is a SMS in the inbox
            #   - Message is unread
            #   - Message is within the past 24 hours (86,400 seconds)
            if (time() - conversation_data['startTime'] < 86400) \
               and ('sms' in conversation_data['labels']) \
               and ('inbox' in conversation_data['labels']):
                # If not initialized, then the -very- last message sent is
                # found. This is used when later detecting new messages.
                if int(conversation_data['startTime']) > self.last_time:
                    self.temp_time = conversation_data['startTime']
                    if conversation_data['id'] in self.conversations:
                        self.conversations[conversation_data['id']].reset_messages()
                    else:
                        self.conversations[conversation_data['id']] = GVConversation(self,
                            conversation_data['id'],
                            conversation_data['phoneNumber'],
                            conversation_data['displayNumber'])
        if self.temp_time == 0:
            self.temp_time = self.last_time
    
    def __check_conversations   (self, sms_list):
        for cid in self.conversations.iterkeys():
            # Traverses down the DOM to get to the proper div that contains all of the SMS data
            # The -1 brings us to the end to retrieve the very last message.
            try:
                conversation_data = sms_list.find_class('gc-message')[0].getparent()
                conversation_data = conversation_data.get_element_by_id(cid).find_class('gc-message-message-display')[-1]
            except KeyError:
                del self.conversations[cid]
            else:
                self.conversations[cid].find_messages(conversation_data)
    
    def check_sms(self):
        """Retrieves the SMS messages from Google's servers to pass to the Parse function."""
        if self.logged_in:
            from urllib2 import Request, urlopen
            sms_list = urlopen(Request(SMSLIST_URL))
            from lxml import html
            # Strip CDATA tags
            sms_list = sms_list.read()
            sms_list = sms_list.replace('<![CDATA[', '').replace(']]>', '')
            sms_list = html.document_fromstring(sms_list)
            self.__find_conversations (sms_list)
            self.__check_conversations(sms_list)
        else:
            raise NotLoggedIn(self.username)
    

class GVConversation:
    """Holds metadata and messages for a given text-message conversation."""
    def __init__(self, account, id, number, display):
        self.account        = account       # Relates back to the Google Voice account
        self.id             = id            # Conversation id used by Google
        self.number         = str(number)   # +15555555555 version of phone number
        self.display        = display       # Display number/name (provided by Google)
        self.hash           = None          # Hash of last conversation
        self.first_check    = True          # First time checking for text messages?
        self.messages       = []            # Stores all GVMessage objects
    
    def __str__(self):
        return '%s (%s)' % (self.display, self.number)
    
    def send_message    (self, message):
        self.account.send_sms(self.number, message)
    
    def reset_messages  (self):
        if not self.first_check:
            self.first_check = True
        self.messages   = []
    
    def find_messages   (self, conversation):
        from time import strftime, localtime
        message_count = len(conversation) - 1
        if len(conversation) > 2 and conversation[2].get('class') == 'gc-message-sms-old': # Google has some messages hidden
            message_count   += len(conversation[2]) - 1
            message_count   =  [0, 1, range(message_count-3), 4] # Preset list styling when Google hides some SMSes.
            count           =  len(message_count[2])+3
        else:
            message_count   = range(message_count+1)
            count           = len(message_count)
        found_unread        = False # Used to detect if last unread message has yet been found.
        def build_hash(message):
            # hash('time message')
            """Builds a unique hash of the message/time combination and count."""
            return hash('%s%s' % (message[2].text, message[1].text))
        def add_message(message):
            """Adds a message object to the class' list of Message objects."""
            if message[0].text.strip() != 'Me:':
                message = GVMessage(message[2].text, message[1].text)
                self.messages.append(message)
        while not found_unread:
            for mid in message_count:
                if self.hash == None: # Must set the hash first /only/ if none already set.
                    self.hash = build_hash(conversation[-1])
                if type(mid) is type([]) and not found_unread:
                    for second_mid in mid:
                        if not found_unread:
                            message = conversation[2][-(second_mid+1)]
                            if self.hash == build_hash(message):
                                found_unread = True
                                if not self.first_check:
                                    add_message(message)
                            else:
                                add_message(message)
                elif not found_unread:
                    message = conversation[-(mid+1)]
                    if self.hash == build_hash(message):
                        found_unread = True
                        if not self.first_check:
                            add_message(message)
                    else:
                        add_message(message)
                else:
                    break
                # HASH fix:
                #   Include either len(conversation) in hash
                #   or just use that as the hash.
        try:
            self.hash = build_hash(conversation[-1])
        except:
            pass
        # The above substrings are simply for proper formatting right now.
    
    def __simple_request(self, url):
        """Makes GET request to Google's httpd to perform action."""
        from urllib2 import Request, urlopen
        urlopen(Request(url))
    
    def archive         (self):
        """Archive conversation via a simple HTTP request."""
        self.__simple_request('%s' % (ARCHIVE_URL + self.id))
        del self
    
    def mark_read       (self):
        """Mark conversation as read via a simple HTTP request."""
        self.__simple_request('%s' % (READ_URL + self.id))
    
    def mark_unread     (self):
        """Mark conversation as unread via a simple HTTP request."""
        self.__simple_request('%s' % (UNREAD_URL + self.id))

class GVMessage:
    """Holds details for each individual text message."""
    def __init__(self, time, message):
        self.time       = time
        self.message    = message
        if type(self.time) is str:
            from time import strptime
            self.time = self.time.strip()
            self.time = strptime(self.time, '%I:%M %p')
    
    def __str__(self):
        from time import strftime
        return '%s:\t%s' % (strftime('%H:%M', self.time), self.message)

class GVUtil:
    """Useful testing-related/user-accessible functions not crucial to smsGV operation."""
    def __init__(self):
        pass
    
    def display_messages(self, account):
        """Formatted display of new text messages."""
        # Not necessary to keep this code in the library,
        # but good for testing for now.
        print 'Messages for %s:' % account
        display = False
        for conversation in account.conversations.itervalues():
            if len(conversation.messages) > 0:
                if not display:
                    display = True
                print '  %s' % ''.join(['-' for i in range(len(conversation.display) + len(conversation.number) + 4)])
                print '  %s:' % conversation
                print '  %s' % ''.join(['-' for i in range(len(conversation.display) + len(conversation.number) + 4)])
                for message in conversation.messages:
                    print '  %s' % message
        if not display:
            print '  None'
