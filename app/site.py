from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired
import enum
from sqlalchemy import Enum

from datetime import datetime, timedelta
import requests
from celery import Celery
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SECRET_KEY'] = os.urandom(32)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
db = SQLAlchemy(app)

app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND')
app.config['DATABASE_URL'] = os.environ.get('DATABASE_URL')

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])
celery.conf.update(app.config)

class WebsiteForm(FlaskForm):
    address = StringField('address', validators=[DataRequired()])

class Results(db.Model):
    _id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(300), unique=False, nullable=True)
    words_count = db.Column(db.Integer, unique=False, nullable=True)
    http_status_code = db.Column(db.Integer)

class TaskStatus (enum.Enum):
    NOT_STARTED = 1
    PENDING = 2
    FINISHED = 3

class Tasks(db.Model):
    _id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(300), unique=False, nullable=True)
    timestamp = db.Column(db.DateTime())
    task_status = db.Column(Enum(TaskStatus))
    http_status = db.Column(db.Integer)

db.create_all()
db.session.commit()

@celery.task
def parse_website_text(_id):
    task = Tasks.query.get(_id)
    task.task_status = 'PENDING'
    db.session.commit()
    address = task.address
    if not (address.startswith('http') and  address.startswith('https')):
        address = 'http://' + address
    with app.app_context():
        res = requests.get(address) 
        words_count=0
        if res.ok:
            words = res.text.split()
            words_count = words.count("Python")
        result = Results(address=address, words_count=words_count, http_status_code=res.status_code)
        task = Tasks.query.get(_id)
        task.task_status = 'FINISHED'
        db.session.add(result)
        db.session.commit()

@app.route('/add_site', methods=['POST', 'GET'])
def website():
    website_form = WebsiteForm(request.form)
    if request.method == 'POST':
        if website_form.validate_on_submit():
            address = request.form.get('address')
            task = Tasks(address=address, timestamp=datetime.now(), task_status='NOT_STARTED')
            db.session.add(task)
            db.session.commit()
            parse_website_text.delay(task._id)
            # parse_website_text(task._id)
            return redirect('/')
        error = "Форма заполнена неправильно: " + str(website_form.errors)
        return render_template('error.html',form=website_form,error = error)
    return render_template('addsite.html', form=website_form)


@app.route('/results')
def get_results():
    results = Results.query.all()
    return render_template('results.html', count_words=results)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)