from flask import Flask
import redis
from redis import StrictRedis
import re
from flask.ext.bootstrap import Bootstrap

app = Flask(__name__)
app.config.from_object("config")
redis_client = StrictRedis(host='127.0.0.1', port=6379, db = 2)
bootstrap=Bootstrap(app)

def remove_span_filter(text):
    pattern = re.compile(r'<span(.*?)</span>', re.S)
    text = re.sub(pattern, '', text)
    return text

app.add_template_filter(remove_span_filter, 'remove_span')

from app import views
