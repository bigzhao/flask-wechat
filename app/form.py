from flask.ext.wtf import Form
from wtforms import TextAreaField, SubmitField
from wtforms.validators import Required,Length


class sendForm(Form):
    message = TextAreaField('请输入...', validators=[Required(),Length(1,100)])
    submit = SubmitField('发送 Send')


