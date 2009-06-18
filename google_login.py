LOGIN_URL = "https://www.google.com/accounts/ServiceLoginAuth?service=grandcentral"
MARK_READ_URL = "https://www.google.com/voice/m/mark?read=1&id="
USER_NAME = ""
USER_PASS = ""

last_check = "2:28 PM"
logged_in = False
def login(username, password):
    from urllib2 import HTTPCookieProcessor, build_opener, install_opener, Request, urlopen
    from cookielib import LWPCookieJar
    cookie_jar = LWPCookieJar("%s.lwp" % username)
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    install_opener(opener)
    from urllib import urlencode
    form_input = urlencode({
        'continue': 'https://www.google.com/voice/m/i/sms/',
    #    'GALX': 'RDw1nbko1nM', # changes? importance?
        'Email': username,
        'Passwd': password,
        'PersistentCookies': 'yes',
    })
    urlopen(Request(LOGIN_URL, form_input, {'Content-type': 'application/x-www-form-urlencoded'}))
    logged_in = True

def mark_read(conversation_ids):
    for cid in conversation_ids:
        from urllib2 import Request, urlopen
        urlopen(Request(MARK_READ_URL + cid))

def sms_parser(sms_page):
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

def sms_check():
    if not logged_in: login(USER_NAME, USER_PASS)
    from urllib2 import Request, urlopen
    req = Request("https://www.google.com/voice/m/i/sms")
    handle = urlopen(req)
    mark_read(sms_parser(handle))
