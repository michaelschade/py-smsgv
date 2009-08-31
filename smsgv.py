# We use the mobile website for everything possible to save on bandwidth
LOGIN_URL       = 'https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral'
SEND_SMS_URL    = 'https://www.google.com/voice/m/sendsms'
READ_URL        = 'https://www.google.com/voice/m/mark?read=1&id='
UNREAD_URL      = 'https://www.google.com/voice/m/mark?read=0&id='
SMSLIST_M_URL   = 'https://www.google.com/voice/m/i/sms'
# We use the main website (instead of mobile) because Google includes helpful data stored via JSON here
SMSLIST_URL     = ('https://www.google.com/voice/inbox/recent/sms',
                   'https://www.google.com/voice/inbox/recent/spam/')
# POST
ARCHIVE_URL     = 'https://www.google.com/voice/inbox/archiveMessages/'
DELETE_URL      = 'https://www.google.com/voice/inbox/deleteMessages/'
DELETE_FOREVER  = 'https://www.google.com/voice/inbox/deleteForeverMessages/'
SPAM_URL        = 'https://www.google.com/voice/inbox/spam/'
STAR_URL        = 'https://www.google.com/voice/inbox/star/'

# Todo: Add multiple pages of messages support

class NotLoggedIn(Exception):
    def __init__(self, username):
        self.username = str(username)
    def __str__(self):
        return self.username

def _simple_post(id, url, data):
    """POSTS data to Google's httpd to perform action."""
    from urllib2 import Request, urlopen
    from urllib import urlencode
    data['_rnr_se'] = id
    data = urlencode(data)
    urlopen(Request(url, data, {'Content-type': 'application/x-www-form-urlencoded'}))

def _simple_get(url):
    """Makes GET request to Google's httpd to perform action."""
    from urllib2 import Request, urlopen
    urlopen(Request(url))

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
        self.temp_time      = 0
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
            _simple_post(self.id, self.id, SEND_SMS_URL, {
                'number':   number,
                'smstext':  message,
            })
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
               and (('sms' in conversation_data['labels'] \
                    and 'inbox' in conversation_data['labels']) \
                    or ('spam' in conversation_data['labels'])): # TODO: Support spam/archive
                # If not initialized, then the -very- last message sent is
                # found. This is used when later detecting new messages.
                if int(conversation_data['startTime']) > self.last_time:
                    self.temp_time = conversation_data['startTime']
                    if conversation_data['id'] in self.conversations:
                        self.conversations[conversation_data['id']].reset_messages()
                        if self.conversations[conversation_data['id']].note != conversation_data['note']:
                            self.conversations[conversation_data['id']].note = conversation_data['note']
                        if self.conversations[conversation_data['id']].read != conversation_data['isRead']:
                            self.conversations[conversation_data['id']].read = conversation_data['isRead']
                        if self.conversations[conversation_data['id']].spam != conversation_data['isSpam']:
                            self.conversations[conversation_data['id']].spam = conversation_data['isSpam']
                        if self.conversations[conversation_data['id']].trash != conversation_data['isTrash']:
                            self.conversations[conversation_data['id']].trash = conversation_data['isTrash']
                        if self.conversations[conversation_data['id']].star != conversation_data['star']:
                            self.conversations[conversation_data['id']].star = conversation_data['star']
                    else:
                        self.conversations[conversation_data['id']] = GVConversation(self,
                            conversation_data['id'],
                            conversation_data['phoneNumber'],
                            conversation_data['displayNumber'],
                            conversation_data['note'],
                            conversation_data['isRead'],
                            conversation_data['isSpam'],
                            conversation_data['isTrash'],
                            conversation_data['star'])
        if self.temp_time == 0:
            self.temp_time = self.last_time
    
    def __check_conversations   (self, sms_list, page='inbox'):
        for cid in self.conversations.iterkeys():
            # Traverses down the DOM to get to the proper div that contains all of the SMS data
            # The -1 brings us to the end to retrieve the very last message.
            try:
                conversation_data = sms_list.find_class('gc-message')[0].getparent().get_element_by_id(cid).find_class('gc-message-message-display')[-1]
            except KeyError:
                if (self.conversations[cid].spam and page == 'spam') \
                  or (not self.conversations[cid].spam and page != 'spam'):
                    del self.conversations[cid]
            except IndexError:
                pass # Happens because of an empty page
            else:
                self.conversations[cid].find_messages(conversation_data)
    
    def __get_page(self, url):
        from urllib2 import Request, urlopen
        sms_list = urlopen(Request(url))
        from lxml import html
        # Strip CDATA tags
        sms_list = sms_list.read()
        sms_list = sms_list.replace('<![CDATA[', '').replace(']]>', '')
        sms_list = html.document_fromstring(sms_list)
        return sms_list
    
    def check_sms(self):
        """Retrieves the SMS messages from Google's servers to pass to the Parse function."""
        if self.logged_in:
            sms_list_inbox  = self.__get_page(SMSLIST_URL[0])
            sms_list_spam   = self.__get_page(SMSLIST_URL[1])
            self.__find_conversations (sms_list_inbox)
            self.__check_conversations(sms_list_inbox)
            self.__find_conversations (sms_list_spam)
            self.__check_conversations(sms_list_spam, 'spam')
        else:
            raise NotLoggedIn(self.username)
    

class GVConversation:
    """Holds metadata and messages for a given text-message conversation."""
    def __init__(self, account, id, number, display, note, read, spam, trash, star):
        self.account        = account       # Relates back to the Google Voice account
        self.id             = id            # Conversation id used by Google
        self.number         = str(number)   # +15555555555 version of phone number
        self.display        = display       # Display number/name (provided by Google)
        self.note           = note
        self.read           = read
        self.spam           = spam
        self.trash          = trash
        self.star           = star
        self.hash           = None          # Hash of last conversation
        self.first_check    = True          # First time checking for text messages?
        self.messages       = []            # Stores all GVMessage objects
    
    def __str__(self):
        return '%s (%s)' % (self.display, self.number)
    
    def send_message    (self, message):
        self.account.send_sms(self.number, message)
    
    def reset_messages  (self):
        if self.first_check:
            self.first_check = False
        self.messages   = []
    
    def find_messages   (self, conversation):
        from time import strftime, localtime
        message_count = len(conversation) - 1
        if len(conversation) > 2 and conversation[2].get('class') == 'gc-message-sms-old': # Google has some messages hidden
            message_count   += len(conversation[2]) - 1
            message_count   =  [0, 1, range(message_count-3), 4] # Preset list styling when Google hides some SMSes.
        else:
            message_count   = range(message_count+1)
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
                                if self.first_check and self.account.initialized:
                                    add_message(message)
                            else:
                                add_message(message)
                elif not found_unread:
                    message = conversation[-(mid+1)]
                    if self.hash == build_hash(message):
                        found_unread = True
                        if self.first_check and self.account.initialized:
                            add_message(message)
                    else:
                        add_message(message)
                else:
                    break
        try:
            self.hash = build_hash(conversation[-1])
        except:
            pass
        # The above substrings are simply for proper formatting right now.
    
    def mark_read       (self):
        """Mark conversation as read via a simple HTTP request."""
        _simple_get('%s' % (READ_URL + self.id))
        self.read = True
    
    def unmark_read     (self):
        """Mark conversation as unread via a simple HTTP request."""
        _simple_get('%s' % (UNREAD_URL + self.id))
        self.read = False
    
    def mark_star       (self):
        _simple_post(self.account.id, STAR_URL, {
            'messages': self.id,
            'star':     1,
        })
        self.star = True
    
    def unmark_star     (self):
        _simple_post(self.account.id, STAR_URL, {
            'messages': self.id,
            'star':     0,
        })
        self.star = False
    
    def archive         (self):
        """Archive conversation via a simple HTTP request."""
        _simple_post(self.account.id, ARCHIVE_URL, {
            'messages': self.id,
            'archive':  1,
        })
        del self.account.conversations[self.id] # Because supporting unarchived
        # messages is not yet supported
    
    def unarchive       (self): # Not currently able to get archived messages to do so,
    # preparing for said functionality
        """Archive conversation via a simple HTTP request."""
        _simple_post(self.account.id, ARCHIVE_URL, {
            'messages': self.id,
            'archive':  0,
        })
    
    def delete          (self):
        _simple_post(self.account.id, DELETE_URL, {
            'messages': self.id,
            'trash':    1,
        })
        self.trash = True
    
    def undelete        (self):
        _simple_post(self.account.id, DELETE_URL, {
            'messages': self.id,
            'trash':    0,
        })
        self.trash = False
        # del self.account.conversations[self.id]
    
    def delete_forever  (self):
        if self.trash or self.spam:
            _simple_post(self.account.id, DELETE_FOREVER_URL, {
                'messages': self.id,
            })
            del self.account.conversations[self.id]
    
    def mark_spam       (self):
        _simple_post(self.account.id, SPAM_URL, {
            'messages': self.id,
            'spam':     1,
        })
        self.spam = True
        del self.account.conversations[self.id]
    
    def unmark_spam     (self): # Not currently able to get spammed messages to do so,
        # preparing for said functionality
        _simple_post(self.account.id, SPAM_URL, {
            'messages': self.id,
            'spam':     0,
        })
        self.spam = False
    

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
        print 'Messages for %s:' % account
        display = False
        for conversation in account.conversations.itervalues():
            if len(conversation.messages) > 0:
                if not display:
                    display = True
                if conversation.spam:
                    spam_display = ''
                else:
                    spam_display = 'Not '
                print '  %s' % ''.join(['-' for i in range(len(conversation.display) + len(conversation.number) + 14)])
                print '  %s, %sSpam:' % (conversation, spam_display)
                print '  %s' % ''.join(['-' for i in range(len(conversation.display) + len(conversation.number) + 14)])
                for message in conversation.messages:
                    print '  %s' % message
        if not display:
            print '  None'
