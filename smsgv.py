__author__		= 'Michael Schade'
__email__		= 'michaelaschade@gmail.com',
__website__     = 'http://www.mschade.me/'
__copyright__	= 'Copyright 2009 Michael Schade'
__credits__		= ['Michael Schade']
__license__		= 'The MIT License'
__version__		= '0.1'
__doc__         = """
py-smsgv:\t%(__copyright__)s
Version:\t%(__version__)s

Originally this was written as a way to interface
the internal Google Voice API in order to (as my
purposes mainly include) mainly retrieve latest
SMS messages. Though, in addition, I had planned
to add other features such as call forwarding,
retrieving voicemails, local numbers, etc.

However, it became apparent to me that someone
else coded something in a similar fashion with
the exact same features. Their project is called
PyGoogleVoice and is located at
http://code.google.com/p/pygooglevoice/. Since
their code is better tested, has had more time
poured into it, and is more full-featured, I have
discontinued this project at its early stage and
instead recommend using PyGoogleVoice.

I had fun coding this, learned a little bit (such
as cjson's efficiency over other json implementations),
and plan now to move on to the personal project of
mine that inspired using this in the first place.
Instead, though, I will make use of PyGoogleVoice
in my project rather than my own implementation.

Thank you,
%(__credits__)s - %(__website__)s
%(__email__)s
"""
# Thanks to PyGoogleVoice (http://code.google.com/p/pygooglevoice/)
# for idea of using variables such as those provided for proper
# doc string data about code.

# We use the mobile website for everything possible to save on bandwidth
MAIN_BASE       = 'https://www.google.com/voice/inbox/'
MOBILE_BASE     = 'https://www.google.com/voice/m/'

SEND_SMS_URL    = MOBILE_BASE + 'sendsms'
READ_URL        = MOBILE_BASE + 'mark?read=1&id='
UNREAD_URL      = MOBILE_BASE + 'mark?read=0&id='
SMSLIST_M_URL   = MOBILE_BASE + 'i/sms'
# We use the main website (instead of mobile) because Google includes helpful data stored via JSON here
LOGIN_URL       = 'https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral'
SMSLIST_URL     = (MAIN_BASE + 'recent/sms',
                   MAIN_BASE + 'recent/spam/')
# POST
ARCHIVE_URL     = MAIN_BASE + 'archiveMessages/'
DELETE_URL      = MAIN_BASE + 'deleteMessages/'
DELETE_FOREVER  = MAIN_BASE + 'deleteForeverMessages/'
SPAM_URL        = MAIN_BASE + 'spam/'
NOTE_URL        = MAIN_BASE + 'savenote/'
DELETE_NOTE_URL = MAIN_BASE + 'deletenote/'
STAR_URL        = MAIN_BASE + 'star/'

# Todo: Add multiple pages of messages support

class NotLoggedIn(Exception):
    def __init__(self, username):
        self.username = str(username)
    def __str__(self):
        return self.username

def Property(func):
    # Thanks to http://adam.gomaa.us/blog/2008/aug/11/the-python-property-builtin/
    return property(**func())

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

class GVAccount(object):
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
        """Sends a text message (SMS) to any supplied number. Seems to bypass 2
        message limit imposed by Google Voice's website. Please do not abuse this!"""
        if self.logged_in:
            _simple_post(self.id, SEND_SMS_URL, {
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
                        self.conversations[conversation_data['id']].clear_local_messages()
                        if self.conversations[conversation_data['id']].note != conversation_data['note']:
                            self.conversations[conversation_data['id']].note = conversation_data['note']
                        if self.conversations[conversation_data['id']].read != conversation_data['isRead']:
                            self.conversations[conversation_data['id']].read = conversation_data['isRead']
                        if self.conversations[conversation_data['id']].spam != conversation_data['isSpam']:
                            self.conversations[conversation_data['id']].spam = conversation_data['isSpam']
                        if self.conversations[conversation_data['id']].deleted != conversation_data['isTrash']:
                            self.conversations[conversation_data['id']].deleted = conversation_data['isTrash']
                        if self.conversations[conversation_data['id']].starred != conversation_data['star']:
                            self.conversations[conversation_data['id']].starred = conversation_data['star']
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
    

class GVConversation(object):
    """Holds metadata and messages for a given text-message conversation."""
    def __init__(self, account, id, number, display, note, read, spam, trash, star):
        self.account        = account       # Relates back to the Google Voice account
        self.id             = id            # Conversation id used by Google
        self.number         = str(number)   # +15555555555 version of phone number
        self.display        = display       # Display number/name (provided by Google)
        self.__note           = note
        self.__read           = read
        self.__spam           = spam
        self.__trash          = trash
        self.__star           = star
        self.hash           = None          # Hash of last conversation
        self.first_check    = True          # First time checking for text messages?
        self.messages       = []            # Stores all GVMessage objects
    
    def __str__(self):
        return '%s (%s)' % (self.display, self.number)
    
    def send_message    (self, message):
        """Sends a text message (SMS) to the other party of the conversation."""
        self.account.send_sms(self.number, message)
    
    def clear_local_messages  (self):
        """Removes all currently stored messages from the object's local storage."""
        if self.first_check:
            self.first_check = False
        self.messages   = []
    
    def find_messages   (self, conversation):
        # Uses a hash of the latest message to help only retrieve the latest messages.
        """Finds the latest messages for a given conversation. Only retrieves
        messages not previously stored in the object."""
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
    
    @Property
    def read():
        doc = 'Marks or unmarks a conversation as read. Accepts boolean values.'
        
        def fget(self):
            return self.__read
        
        def fset(self, is_read):
            """Mark conversation as unread via a simple HTTP request."""
            if is_read:
                url = READ_URL
            else:
                url = UNREAD_URL
            _simple_get('%s' % (url + self.id))
            self.__read = int(is_read)
        
        return locals()
    
    @Property
    def starred():
        doc = 'Marks or unmarks a conversation as starred. Accepts boolean values.'
        
        def fget(self):
            return self.__star
        
        def fset(self, is_starred):
            _simple_post(self.account.id, STAR_URL, {
                'messages': self.id,
                'star':     int(is_starred),
            })
            self.__star = int(is_starred)
        
        return locals()
    
    @Property
    def archived():
        doc = "(Un)archives a conversation on Google's servers. Accepts boolean values."
        
        def fget(self):
            pass
            # return self.__archived
        
        def fset(self, is_archived):
            """Archive conversation via a simple HTTP request."""
            _simple_post(self.account.id, ARCHIVE_URL, {
                'messages': self.id,
                'archive':  int(is_archived)
            })
            #del self.account.conversations[self.id]
        
        return locals()
    
    @Property
    def deleted():
        doc = 'Moves a conversation to or from the trash. Accepts boolean values.'
        
        def fget(self):
            return self.__trash
        
        def fset(self, is_deleted):
            _simple_post(self.account.id, DELETE_URL, {
                'messages': self.id,
                'trash':    int(is_deleted),
            })
            self.__trash = int(is_deleted)
        
        return locals()
    
    def delete_forever(self):
        """Permanently deletes the conversation from Google's servers."""
        if self.__trash or self.__spam:
            _simple_post(self.account.id, DELETE_FOREVER_URL, {
                'messages': self.id,
            })
            del self.account.conversations[self.id]
    
    @Property
    def spam():
        doc = 'Marks or unmarks a conversation as spam. Accepts boolean values.'
        
        def fget(self):
            return self.__spam
        
        def fset(self, is_spam): # Not currently able to get spammed messages to do so,
            # preparing for said functionality
            _simple_post(self.account.id, SPAM_URL, {
                'messages': self.id,
                'spam':     int(is_spam)
            })
            self.__spam     = int(is_spam)
        
        return locals()
    
    @Property
    def note():
        doc = "Adds, changes, or deletes a conversation's note."
        
        def fget(self):
            return self.__note
        
        def fset(self, message):
            _simple_post(self.account.id, NOTE_URL, {
                'id':   self.id,
                'note': message,
            })
            self.__note = message
        
        def fdel(self):
            _simple_post(self.account.id, DELETE_NOTE_URL, {
                'id':   self.id,
            })
            self.__note = ''
        
        return locals()
    

class GVMessage(object):
    """Holds details for each individual text message."""
    def __init__(self, time, message):
        # If string provided for time, converted to a time object.
        """Accepts time in format of %%I:%%M %%p (HH:MM AM/PM) or a time
        object. Message limit """
        self.time       = time
        self.message    = message
        if type(self.time) is str:
            from time import strptime
            self.time = self.time.strip()
            self.time = strptime(self.time, '%I:%M %p')
    
    def __str__(self):
        from time import strftime
        return '%s:\t%s' % (strftime('%H:%M', self.time), self.message)
    

class GVUtil(object):
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
                for message in conversation.messages[::-1]:
                    print '  %s' % message
        if not display:
            print '  None'
    
