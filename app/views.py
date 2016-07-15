from app import app
from flask import render_template, request, redirect, session, url_for
from .wechat_api import WebWechatApi
import json
import os
from . import redis_client
from .form import sendForm
import re

TEMP_PATH = os.path.join(os.getcwd(), 'tmp')
WX = WebWechatApi()

SPECIAL_USER = (
    'newsapp', 'fmessage', 'filehelper', 'weibo', 'qqmail', 'fmessage',
    'tmessage', 'qmessage', 'qqsync', 'floatbottle', 'lbsapp', 'shakeapp',
    'medianote', 'qqfriend', 'readerapp', 'blogapp', 'facebookapp', 'masssendapp',
    'meishiapp', 'feedsapp', 'voip', 'blogappweixin', 'weixin', 'brandsessionholder',
    'weixinreminder', 'wxid_novlwrv3lqwv11', 'gh_22b87fa7cb3c', 'officialaccounts',
    'notification_messages', 'wxid_novlwrv3lqwv11', 'gh_22b87fa7cb3c', 'wxitil',
    'userexperience_alarm', 'notification_messages'
)

@app.route('/')
def index():
    global WX 
    qr_code_url = WX.get_qr_image()
    return render_template('qr_scan.html', qr_code_url=qr_code_url, uuid=WX.uuid)


@app.route('/check-login/<uuid>')
def check_login(uuid):
    global WX 
    WX.uuid = uuid
    print("start")
    while True:
        state_code=WX.wait_for_login()
        if state_code == '200':
            break
        elif state_code == '408':  #超时
            print("超时")
            return '408'
    if not WX.init():
        raise Exception('wxinit')
    WX.start_heartbeat_loop()
    WX.user_info['filename'] = ''.join([WX.user_info['UserName'], '/', WX.user_info['UserName'], '.jpg'])


    return str(WX.user_info['UserName'])
    

@app.route('/wechat/<username>')
def wechat_index(username):
     global WX
     WX.webwxgeticon(WX.user_info['UserName'])
#获取头像信息
     for user in WX.contact_list:
         WX.webwxgeticon(user['UserName'])

     return render_template('index.html',user_message=WX.user_info, data = WX.contact_list)


@app.route('/wechat/<username>/<friendname>', methods=['POST', 'GET'])
def wechat_friend(username, friendname):
    form = sendForm()
    global WX
    if friendname not in WX.session:
        WX.session[friendname] = []
    if form.validate_on_submit():
        message = form.message.data
        if WX.webwxsendmsg(message, friendname):
            WX.session[friendname].append('send:'+message)
            print('[消息发送成功]')
        else:
            print('[消息发送失败]') 

        redirect(url_for('wechat_friend', username=username, friendname=friendname))
    user_message = WX.user_info
    data = WX.contact_list[:]
    friendInfo=WX.get_info_by_username(friendname)
    data.remove(friendInfo)

    if WX.has_new_messages(friendInfo):
        WX.remove_new_message_member(friendInfo)

    return render_template('index_friend.html', form=form, data=data,
               user_message=user_message, messages=WX.session[friendname], 
               friendInfo=friendInfo, new_message_members=WX.get_new_message_members())


@app.route('/wechat/checkNews')
def check():
    global WX
    if WX.check_news():
        new_messages = WX.get_new_messages()
        print('prepare return news', new_messages)

        response = {'from': new_messages['from'],'to':new_messages['to'], 
                    'content':new_messages['content'] }

      
        return json.dumps(response)
    else:
        return ''
             

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

