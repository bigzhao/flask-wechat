import ssl
import os
import signal
import requests
import time
import re
import xml.dom.minidom
import sys
import subprocess
import webbrowser
import json
import threading
import random
import copy
from collections import defaultdict

DEBUG = True
TEMP_PATH = os.path.join(os.getcwd(), 'tmp')
QR_IMAGE_PATH = os.path.join(TEMP_PATH, 'qrcode.jpg')
DEVICE_ID = 'e000000000000000'
HEARTBEAT_FREQENCY = 0.1 # minimum gap between two heartbeat packet
# map of push_uri and base_uri
MAP_URI = (
    ('wx2.qq.com', 'webpush2.weixin.qq.com'),
    ('qq.com', 'webpush.weixin.qq.com'),
    ('web1.wechat.com', 'webpush1.wechat.com'),
    ('web2.wechat.com', 'webpush2.wechat.com'),
    ('wechat.com', 'webpush.wechat.com'),
    ('web1.wechatapp.com', 'webpush1.wechatapp.com'),
)
SPECIAL_USER = (
    'newsapp', 'fmessage', 'filehelper', 'weibo', 'qqmail', 'fmessage',
    'tmessage', 'qmessage', 'qqsync', 'floatbottle', 'lbsapp', 'shakeapp',
    'medianote', 'qqfriend', 'readerapp', 'blogapp', 'facebookapp', 'masssendapp',
    'meishiapp', 'feedsapp', 'voip', 'blogappweixin', 'weixin', 'brandsessionholder',
    'weixinreminder', 'wxid_novlwrv3lqwv11', 'gh_22b87fa7cb3c', 'officialaccounts',
    'notification_messages', 'wxid_novlwrv3lqwv11', 'gh_22b87fa7cb3c', 'wxitil',
    'userexperience_alarm', 'notification_messages'
)
# SYNC_HOST = (
#     'webpush.weixin.qq.com',
#     'webpush2.weixin.qq.com',
#     'webpush.wechat.com',
#     'webpush1.wechat.com',
#     'webpush2.wechat.com',
#     'webpush1.wechatapp.com',
#     # 'webpush.wechatapp.com'
# )

def write_to_file(name, data, mode = 'w'):
    with open(os.path.join(TEMP_PATH, name), mode) as f:
        f.write(str(data))

def print_msg(msg_type, content):
    if not isinstance(content, tuple):
        content = (content,)
    printf_msg(msg_type, '%s', ' '.join(str(x) for x in content))

def printf_msg(msg_type, format, content):
    # type: INFO , WARN , ERROR, DEBUG
    if not DEBUG and msg_type == 'DEBUG': return
    if not isinstance(content, tuple):
        content = (content,)
    print('[%s] %s ' % (msg_type, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())) + format % content)

class WebWechatApi():

    uuid = ''
    requests = None
    base_request = {}
    pass_ticket = ''
    tip = 0 # for QR code
    base_uri = ''
    push_uri = ''
    user_info = {}
    sync_key = {}
    cookies = None
    wxuin = ''
    wxsid = ''
    skey = ''

    member_list = []
    contact_list = []
    group_list = []
    group_member_list = []
    special_user_list = []
    public_user_list = []

    heartbeat_thread_handler = None
    sync_listener = []
#自增变量
    logout_status = 0
    session = {}
    new_message_members = []    #新消息的成员，存放字典
    username2info = {}     #mapping username 和 friend info
    messages = []
    new_message_num = 0
    saveFolder = os.path.join(os.getcwd(), 'app', 'static')
    saveSubFolders = {'webwxgeticon': 'icons', 'webwxgetheadimg': 'headimgs', 'webwxgetmsgimg': 'msgimgs',
                               'webwxgetvideo': 'videos', 'webwxgetvoice': 'voices', '_showQRCodeImg': 'qrcodes'}
    #############
    #  BaseApi  #
    #############

    def __init__(self):
        # create requests object
        headers = {
            'User-agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.87 Safari/537.36',
            'Referer': 'https://wx.qq.com/',
            'Origin': 'https://wx.qq.com',
            'Host': 'wx.qq.com',
            'Connection': 'keep-alive'
        }
        self.requests = requests.Session()
        self.requests.headers.update(headers)
        self.requests.mount('http://', requests.adapters.HTTPAdapter(max_retries = 5))
        self.requests.mount('https://', requests.adapters.HTTPAdapter(max_retries = 5))
       

    def _get(self, url, params = None, headers = None):
        r = self.requests.get(url = url, params = params, headers = headers)
        r.encoding = 'utf-8'
        return r

    def _post(self, url, data = None, headers = None, json_fmt = False):
        headers = {'content-type': 'application/json; charset=UTF-8'} if json else {}
        print('headers', headers)
        r = self.requests.post(url = url, data = json.dumps(data), headers = headers) # json.dumps is important here
        r.encoding = 'utf-8'
        return r

    def _get_uuid(self):

        url = 'https://login.weixin.qq.com/jslogin'
        params = {
            'appid': 'wx782c26e4c19acffb',
            'fun': 'new',
            'lang': 'zh_CN',
            '_': int(time.time()),
        }
        data = self._get(url = url, params = params).text
        print_msg('DEBUG', data)

        # response format:
        # window.QRLogin.code = 200; window.QRLogin.uuid = "oZwt_bFfRg==";
        regexp = r'window.QRLogin.code = (\d+); window.QRLogin.uuid = "(\S+?)"'
        pm = re.search(regexp, data)
        state_code, self.uuid = pm.group(1), pm.group(2)

        return state_code == '200'

    def get_qr_image(self):
        if not self._get_uuid():
            return None
        print('https://login.weixin.qq.com/qrcode/' + self.uuid)
        return 'https://login.weixin.qq.com/qrcode/' + self.uuid

    def wait_for_login(self):
        url = 'https://login.weixin.qq.com/cgi-bin/mmwebwx-bin/login?tip=%s&uuid=%s&_=%s' % (
            self.tip, self.uuid, int(time.time()))
        data = self._get(url = url).text
        print_msg('DEBUG', data)

        # response format:
        # window.code=200;window.redirect_uri="<strong>https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage?ticket=80e3b62801bd4063ae6cf1928540da6d&uuid=787fef9712bd46&lang=zh_CN&scan=1434694049</strong>";
        regexp = r'window.code=(\d+);'
        pm = re.search(regexp, data)
        state_code = pm.group(1)

        if state_code == '201':  # scanned
            print_msg('INFO', 'QR Scanned. Please allow web login from Wechat mobile app')
            self.tip = 0
        elif state_code == '200':  # login...
            print_msg('INFO', 'Login...')

            regexp = r'window.redirect_uri="(\S+?)";'
            pm = re.search(regexp, data)
            redirect_uri = pm.group(1) + '&fun=new'
            self.base_uri = redirect_uri[:redirect_uri.rfind('/')]
            print_msg('DEBUG', (redirect_uri, self.base_uri))

            self.push_uri = self.base_uri
            for (s, p) in MAP_URI:
                if self.base_uri.find(s) >= 0:
                    self.push_uri = 'https://%s/cgi-bin/mmwebwx-bin' % p
                    break

            r = self._get(url = redirect_uri)
            data = r.text
            print_msg('DEBUG', data)

            doc = xml.dom.minidom.parseString(data)
            root = doc.documentElement
            for node in root.childNodes:
                if node.nodeName == 'skey':
                    self.skey = node.childNodes[0].data
                elif node.nodeName == 'wxsid':
                    self.wxsid = node.childNodes[0].data
                elif node.nodeName == 'wxuin':
                    self.wxuin = node.childNodes[0].data
                elif node.nodeName == 'pass_ticket':
                    self.pass_ticket = node.childNodes[0].data
            printf_msg('DEBUG', 'skey: %s, wxsid: %s, wxuin: %s, pass_ticket: %s', (self.skey, self.wxsid, self.wxuin, self.pass_ticket))

            if not all((self.skey,self.wxsid, self.wxuin, self.pass_ticket)):
                print_msg('ERROR', 'Login error #2')

            self.base_request = {
                'Uin': int(self.wxuin),
                'Sid': self.wxsid,
                'Skey': self.skey,
                'DeviceID': DEVICE_ID,
            }

            # close QR image and remove
            pass

        elif state_code == '408':  # timeout
            print_msg('ERROR', 'Time out')
        else:
            print_msg('ERROR', 'Login error')

        return state_code 

    def _saveFile(self, filename, data):
        fn = filename
        dirName = os.path.join(self.saveFolder, self.user_info['UserName'])
        if not os.path.exists(dirName):
            os.makedirs(dirName)
        fn = os.path.join(dirName, filename)
        with open(fn, 'wb') as f:
            f.write(data)
            f.close()
        return fn

    def webwxgeticon(self, id):
        url = self.base_uri + \
            '/webwxgeticon?username=%s&skey=%s' % (id, self.skey)
        data = self._get(url)
        fn = id + '.jpg'
        return self._saveFile(fn, data.content)



    def response_state(self, func, base_response):
        err_msg = base_response['ErrMsg']
        ret = base_response['Ret']
        if ret == '1101' or ret == '1100':
            print_msg('INFO', 'logout')
            os._exit(1)
        if ret != 0:
            printf_msg('ERROR', 'Func: %s, Ret: %d, ErrMsg: %s', (func, ret, err_msg))
        elif DEBUG:
            printf_msg('INFO', 'Func: %s, Ret: %d, ErrMsg: %s', (func, ret, err_msg))

        return ret == 0

    def init(self):
        url = '%s/webwxinit?pass_ticket=%s&skey=%s&r=%s' % (
            self.base_uri, self.pass_ticket, self.base_request['Skey'], int(time.time()))
        params = {'BaseRequest': self.base_request}

        r = self._post(url = url, data = params, json_fmt = True)
        data = r.json()

        state = self.response_state('webwxinit', data['BaseResponse'])
        if not state:
            return False

        if DEBUG:
            write_to_file('webwxinit.json', r.content)

        # self.contact_list = data['ContactList']
        self.user_info = data['User']
        self.sync_key = data['SyncKey']

        return self._status_notify() and self._get_contact() and self._batch_get_contact()

    def _status_notify(self):
        url = '%s/webwxstatusnotify?&pass_ticket=%s' % (self.base_uri, self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            "Code": 3,
            "FromUserName": self.user_info['UserName'],
            "ToUserName": self.user_info['UserName'],
            "ClientMsgId": int(time.time())
        }
        data = self._post(url = url, data = params, json_fmt = True).json()

        return self.response_state('webwxstatusnotify', data['BaseResponse'])

    def _get_contact(self):
        url = '%s/webwxgetcontact?pass_ticket=%s&skey=%s&r=%s' % (
            self.base_uri, self.pass_ticket, self.base_request['Skey'], int(time.time()))

        r = self._post(url = url, json_fmt = True)
        data = r.json()

        state = self.response_state('webwxgetcontact', data['BaseResponse'])
        if not state:
            return False

        if DEBUG:
            write_to_file('webwxgetcontact.json', r.content)

        self.member_list = data['MemberList']
        self.contact_list = self.member_list[:]
        for m in self.member_list:
            m['filename'] = ''.join([self.user_info['UserName'], '/', m['UserName'], '.jpg'])
           #自己增加一个list，名字与Nick对应
            self.username2info[m['UserName']] = m
        for i in range(len(self.member_list) - 1, -1, -1):
            contact = self.contact_list[i]
           
            if contact['VerifyFlag'] & 8 != 0:  # public / service
                del self.contact_list[i]
                self.public_user_list.append(contact)
            elif contact['UserName'] in SPECIAL_USER:  # special user
                del self.contact_list[i]
                self.special_user_list.append(contact)
            elif contact['UserName'].find('@@') != -1:  # group
                del self.contact_list[i]
                self.group_list.append(contact)
            elif contact['UserName'] == self.user_info['UserName']:  # self
                del self.contact_list[i]

        if DEBUG:
            write_to_file('webwxgetcontact_contact.json', json.dumps(self.contact_list, indent = 4))
            write_to_file('webwxgetcontact_group.json', json.dumps(self.group_list, indent = 4))
            write_to_file('webwxgetcontact_special.json', json.dumps(self.special_user_list, indent = 4))
            write_to_file('webwxgetcontact_public.json', json.dumps(self.public_user_list, indent = 4))

        return True

#自增一个用username求nickname
    def get_info_by_username(self, username):
        return self.username2info[username]

   
    def _batch_get_contact(self):
        url = '%s/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (
                self.base_uri, int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            "Count": len(self.group_list),
            "List": [{"UserName": g['UserName'], "EncryChatRoomId":""} for g in self.group_list]
        }
        
        data = self._post(url = url, data = params, json_fmt = True).json()
        state = self.response_state('webwxbatchgetcontact', data['BaseResponse'])
        if not state:
            return False

        self.group_list = data['ContactList']
        for g in self.group_list:
            member_list = g['MemberList']
            for m in member_list:
                self.group_member_list.append(m)
        return True

    def _get_user_by_id(self, id):
        url = '%s/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (
                self.base_uri, int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            "Count": 1,
            "List": [{"UserName": id, "EncryChatRoomId": ""}]
        }
        data = self._post(url = url, data = params, json_fmt = True).json()
        state = self.response_state('webwxbatchgetcontact', data['BaseResponse'])
        if not state:
            return False

        return data['ContactList']

    def add_sync_listener(self, callback):
        self.sync_listener.append(callback)

    def start_heartbeat_loop(self):
        self.heartbeat_thread_handler = threading.Thread(target = self._heartbeat_thread)
        print_msg('DEBUG', 'heartbeat loop start...')
        self.heartbeat_thread_handler.start()

    def _heartbeat_thread(self):
        while True:
            if self.logout_status:
                self.logout_status = 0
                break
            last_check_time = time.time()
            selector = self._sync_check()
            if selector != '0':
                data = self._sync()
                if not data:
                    print_msg('ERROR', 'heartbeat thread sync')

                if selector == '2': # new message
                    self.handleMsg(data)

            if time.time() - last_check_time <= HEARTBEAT_FREQENCY:
                time.sleep(time.time() + HEARTBEAT_FREQENCY - last_check_time)

    def _searchContent(self, key, content, fmat='attr'):
        if fmat == 'attr':
            pm = re.search(key + '\s?=\s?"([^"<]+)"', content)
            if pm:
                return pm.group(1)
        elif fmat == 'xml':
            pm = re.search('<{0}>([^<]+)</{0}>'.format(key), content)
            if not pm:
                pm = re.search(
                    '<{0}><\!\[CDATA\[(.*?)\]\]></{0}>'.format(key), content)
            if pm:
                return pm.group(1)
        return '未知'
#新增接口
    def _showMsg(self, message):
        srcName = None
        dstName = None
        groupName = None
        content = None
        
        msg = message

        if msg['raw_msg']:
            srcName = msg['raw_msg']['FromUserName']
            dstName = msg['raw_msg']['ToUserName']
            content = msg['raw_msg']['Content'].replace(
                '&lt;', '<').replace('&gt;', '>')
            message_id = msg['raw_msg']['MsgId']

            if content.find('http://weixin.qq.com/cgi-bin/redirectforward?args=') != -1:
                print('[NEW] 位置消息')
                # 地理位置消息
                content = '发送了一个位置消息 -'

                    

            if msg['raw_msg']['ToUserName'] == 'filehelper':
                print('[NEW] 文件传输助手')
                # 文件传输助手
                dstName = '文件传输助手'

            if msg['raw_msg']['FromUserName'][:2] == '@@':
                # 接收到来自群的消息
                content = '群消息, 请在手机上察看'
            elif msg['raw_msg']['ToUserName'][:2] == '@@':
                # 自己发给群的消息
                content = '群消息, 请在手机上察看'

            # 收到了红包
            if content == '收到红包，请在手机上查看':
                msg['message'] = content

            # 指定了消息内容
            if 'message' in msg.keys():
                content = msg['message']
#为消息内容标明发送接收方
        content = ('发送:' if srcName == self.user_info['UserName'] else '收到:') + content    
#增加消息
        self.messages.append({'from':srcName, 'to':dstName, 'content':content})
#是发送方
        if self.user_info['UserName'] == srcName:
            print('[send] 发送方')
            if dstName in self.session.keys():
                print('[session]', self.session)
                print('[content]', content)
                self.session[dstName].append(content)
            else:
                self.session[dstName]= [content,]    
            if dstName in self.username2info:
                u = self.username2info[dstName]   
                if(u in self.contact_list) and (u not in self.new_message_members):    
                    self.new_message_members.insert(0, u)   #在首位插入mappin
#是接受方
        else:
            print('[receive] 接受方')
            if srcName in self.session.keys():
                print('[session]', self.session)
                print('[content]', content)
                self.session[srcName].append(content)
            else:
                self.session[srcName]= [content,]     
            if srcName in self.username2info:
                u = self.username2info[srcName]
                if u not in self.new_message_members:
                    if(u in self.contact_list) and (u not in self.new_message_members):      
                        self.new_message_members.insert(0, u)   #在首位插入mappin
        print('[+1] 新消息+1')
        self.new_message_num += 1


    def handleMsg(self, r):
        for msg in r['AddMsgList']:
            print('[*] 你有新的消息，请注意查收')
            msgType = msg['MsgType']
            content = msg['Content'].replace('&lt;', '<').replace('&gt;', '>')
            msgid = msg['MsgId']

            if msgType == 1:
                print('[type] 1')            
                raw_msg = {'raw_msg': msg}
                self._showMsg(raw_msg)

            elif msgType == 3:
                print('[type] 3')     
                raw_msg = {'raw_msg': msg,
                           'message': '一张图片,请在手机上察看' }
                self._showMsg(raw_msg)

            elif msgType == 34:
                print('[type] 34')     
                raw_msg = {'raw_msg': msg,
                           'message': '一段语音，请在手机上察看'}
                self._showMsg(raw_msg)
            elif msgType == 42:
                print('[type] 42')     
                raw_msg = {'raw_msg': msg, 
                           'message': '一张名片: %s,请在手机上察看' % ( json.dumps(info))}
                self._showMsg(raw_msg)
            elif msgType == 47:
                print('[type] 47')     
                url = self._searchContent('cdnurl', content)
                raw_msg = {'raw_msg': msg,
                           'message': '一个动画表情，点击下面链接查看: %s' % ( url)}
                self._showMsg(raw_msg)

            elif msgType == 49:
                print('[type] 49')     
                raw_msg = {'raw_msg': msg, 'message': '一个公众号/订阅号推送,请在手机上察看' }
                self._showMsg(raw_msg)
            elif msgType == 51:#成功获取联系人信息
                print('[type] 51')     
                 
            elif msgType == 62:
                print('[type] 62')     
                video = self.webwxgetvideo(msgid)
                raw_msg = {'raw_msg': msg,
                           'message': '发了一段小视频,请在手机上察看'}
                self._showMsg(raw_msg)
            elif msgType == 10002:
                print('[type] 10002')     
                raw_msg = {'raw_msg': msg, 'message': '撤回了一条消息' }
                self._showMsg(raw_msg)
            else:
                print('[type] 其他')     
                raw_msg = {
                    'raw_msg': msg, 'message': '[*] 该消息类型为: %d，可能是表情，图片, 链接或红包' % msg['MsgType']}
                self._showMsg(raw_msg)

    def check_news(self):
        if self.new_message_num != 0:
            return True
        else:
            return False

    def get_new_messages(self):
        new_messages = self.messages[-1]
        self.new_message_num -= 1
        print(new_messages)
        return new_messages
        
    def get_new_message_members(self):
        return self.new_message_members

    def remove_new_message_member(self, user):
        self.new_message_members.remove(user)
        return

    def has_new_messages(self, username):
        if username in self.new_message_members:
            return True
        return False
####
    def _sync_key_str(self):
        return '|'.join(['%s_%s' % (item['Key'], item['Val']) for item in self.sync_key['List']])

    def _sync_check(self):
        check_start_time = time.time()
        url = self.push_uri + '/synccheck'
        curr_time = int(time.time())
        params = {
            'skey': self.base_request['Skey'],
            'sid': self.base_request['Sid'],
            'uin': self.base_request['Uin'],
            'deviceId': self.base_request['DeviceID'],
            'synckey': self._sync_key_str(),
            'r': curr_time,
            '_': curr_time,
        }
        headers = {'Connection': 'Keep-Alive'} # long polling

        data = self._get(url = url, params = params, headers = headers).text
        printf_msg('DEBUG', 'heartbeat syncheck %ds', round(time.time() - check_start_time, 2))

        # response format
        # window.synccheck={retcode:"0", selector:"2"}
        regexp = r'window.synccheck={retcode:"(\d+)",selector:"(\d+)"}'
        pm = re.search(regexp, data)
        retcode, selector = pm.group(1), pm.group(2)

        if retcode != '0':
            print_msg('INFO', 'logout')
            os._exit(1)

        return selector

    def _sync(self):
        url = '%s/webwxsync?lang=zh_CN&skey=%s&sid=%s&pass_ticket=%s' % (
            self.base_uri, self.base_request['Skey'], self.base_request['Sid'], self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            'SyncKey': self.sync_key,
            'rr': ~int(time.time()),
        }

        r = self._post(url = url, data = params, json_fmt = True)
        data = r.json()
        # print(data)

        state = self.response_state('webwxsync', data['BaseResponse'])
        if not state:
            return None

        self.sync_key = data['SyncKey']
        return data


    def webwxsendmsg(self, word, to='filehelper'):
        url = self.base_uri + \
            '/webwxsendmsg?pass_ticket=%s' % (self.pass_ticket)
        clientMsgId = str(int(time.time() * 1000)) + \
            str(random.random())[:5].replace('.', '')
        params = {
            'BaseRequest': self.base_request,
            'Msg': {
                "Type": 1,
                "Content": word,
                "FromUserName": self.user_info['UserName'],
                "ToUserName": to,
                "LocalID": clientMsgId,
                "ClientMsgId": clientMsgId
            }
        }
        headers = {'content-type': 'application/json; charset=UTF-8'}
        data = json.dumps(params, ensure_ascii=False).encode('utf8')
        r = requests.post(url, data=data, headers=headers)
        dic = r.json()
        return dic['BaseResponse']['Ret'] == 0


    def logout(self):
        self.logout_status = 1
        time.sleep(3)
        url = '%s/webwxlogout?redirect=1&type=0&skey=%s' % (self.base_uri, self._sync_key_str())
        params = {
            'sid': self.base_request['Sid'],
            'uin': self.base_request['Uin']
        }
        self._post(url = url, data = params, json_fmt = True)
        print_msg('INFO', 'logout')


    #############
    #  Utility  #
    #############

    # method could be local, web
    def show_qr_image(self, url, method = 'local'):
        print_msg('INFO', 'Please use Wechat mobile app to scan QR image')
        self.tip = 1

        if method == 'web':
            webbrowser.open_new_tab(url)
            return
        else:
            params = {
                't': 'webwx',
                '_': int(time.time()),
            }
            data = self._get(url = url, params = params).content

            write_to_file(QR_IMAGE_PATH, data)
            time.sleep(1)

            if sys.platform.find('darwin') >= 0: subprocess.call(('open', QR_IMAGE_PATH))
            elif sys.platform.find('linux') >= 0: subprocess.call(('xdg-open', QR_IMAGE_PATH))
            elif sys.platform.find('win32') >= 0: subprocess.call(('cmd', '/C', 'start', QR_IMAGE_PATH))
            else: os.startfile(QR_IMAGE_PATH)

    def get_user_id(self, name):
        for m in self.member_list:
            if name == m['RemarkName'] or name == m['NickName']:
                return m['UserName']
        return None

    def _get_group_name(self, id):
        for m in self.group_member_list:
            if m['UserName'] == id:
                return m['NickName']
        
        # not found
        name = 'unknown'
        group_list = self._get_user_by_id(id)
        for g in group_list:
            self.group_list.append(g)
            if g['UserName'] == id:
                name = g['NickName']
                member_list = g['MemberList']
                for m in member_list:
                    self.group_member_list.append(m)
        return name

    def get_user_remark_name(self, id):
        if id == self.user_info['UserName']: # self
            return self.user_info['NickName']

        if id[:2] == '@@': # group
            for m in self.group_list:
                self._get_group_name(id)
        else:
            # contact
            for m in self.contact_list:
                if m['UserName'] == id:
                    return m['RemarkName'] if m['RemarkName'] else m['NickName']

            # special
            for m in self.special_user_list:
                if m['UserName'] == id:
                    name = m['RemarkName'] if m['RemarkName'] else m['NickName']
                    return name

            # public
            for m in self.public_user_list:
                if m['UserName'] == id:
                    return m['RemarkName'] if m['RemarkName'] else m['NickName']

            # group member
            for m in self.group_member_list:
                if m['UserName'] == id:
                    return m['DisplayName'] if m['DisplayName'] else m['NickName']

        return 'unknown'

def sync_handler(wx, data):
    print ('New data comes:', data)

if __name__ == '__main__':
    try:
        wx = WebWechatApi()
        wx.add_sync_listener(sync_handler)

        wx.show_qr_image(wx.get_qr_image())
        while wx.wait_for_login() != '200':
            pass
        if not wx.init():
            raise Exception('wxinit')
        wx.start_heartbeat_loop()

    except Exception as e:
        print(e)

