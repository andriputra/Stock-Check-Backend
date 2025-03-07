from flask import Flask

app = Flask(__name__)

class Config:
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'orderrequisition'
    MYSQL_CURSORCLASS = 'DictCursor'
    SECRET_KEY = 'your_secret_key'

app.config['SESSION_COOKIE_SAMESITE'] = "None"
app.config['SESSION_COOKIE_SECURE'] = True