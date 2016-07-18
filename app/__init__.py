from flask import Flask
import re
from flask.ext.bootstrap import Bootstrap

app = Flask(__name__)
app.config.from_object("config")
bootstrap=Bootstrap(app)

def remove_span_filter(text):
    pattern = re.compile(r'<span(.*?)</span>', re.S)
    text = re.sub(pattern, '', text)
    return text

app.add_template_filter(remove_span_filter, 'remove_span')

from app import views
