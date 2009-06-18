from settings import USER, PASS # For testing purposes

LOGIN_URL = "https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral"
MARK_READ_URL = "https://www.google.com/voice/m/mark?read=1&id="

#last_check = "2:28 PM"
logged_in = False

class User():
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.logged_in = False
    
    def __markRead(self, conversation_ids):
        for cid in conversation_ids:
            from urllib2 import Request, urlopen
            urlopen(Request(MARK_READ_URL + cid))
    
    def __smsParser(self, sms_page):
        from lxml import html
        parsed_html = html.fromstring(sms_page.read())
        message_ids = set()
        
        # We're only looking for new messages
        for unread_message in parsed_html.find_class("ms3"):
            if unread_message.getparent().get("class") == "mu":
                for piece in unread_message.find_class("ms"):
                    for sender in piece.getprevious().getprevious().find_class("sf"):
                        # We only want the sender's messages
                        if sender.text_content().strip(' ').strip('\n').strip(' ') == "Me:": # Clean up the format for checking. Is there a prettier way to do this?
                            break
                        else:
                            print " %s %s" % (piece.getprevious().text, piece.text.rstrip("()"))
                            message_ids.add(piece.getparent().getparent().getparent().get("id"))
        return message_ids # returns set of ids that were parsed
    
    def login(self):
        from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
        from cookielib import LWPCookieJar
        cookie_jar = LWPCookieJar("%s.lwp" % self.username)
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        install_opener(opener)
        from urllib import urlencode
        form_input = urlencode({
            'continue': 'https://www.google.com/voice/m/i/sms/',
        #    'GALX': 'RDw1nbko1nM', # changes? importance?
            'Email': self.username,
            'Passwd': self.password,
            'PersistentCookies': 'yes',
        })
        urlopen(Request(LOGIN_URL, form_input, {'Content-type': 'application/x-www-form-urlencoded'}))
        self.logged_in = True
    
    def smsCheck(self):
        if not self.logged_in: self.login(USER_NAME, USER_PASS)
        from urllib2 import Request, urlopen
        req = Request("https://www.google.com/voice/m/i/sms")
        handle = urlopen(req)
        self.__markRead(self.__smsParser(handle))

x = User(USER, PASS)
x.login()
x.smsCheck()
