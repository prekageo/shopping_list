#!/usr/bin/env python3

import flask
import json
import sqlite3
import re

DB_FILENAME = 'file:shopping_list.sqlite'
app = flask.Flask(__name__)

class DB():
    def __init__(self, filename):
        self.filename = filename

    def __enter__(self):
        self.conn = sqlite3.connect(self.filename, uri=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('create table if not exists log (timestamp, ip, user_agent, lat, lng, method, data, exception, item_id, title, emojis, quantity, checked)')
        self.conn.execute('create table if not exists items (id integer primary key autoincrement, title, emojis, quantity, checked, unique (title collate nocase))')
        return self

    def __exit__(self, type, value, traceback):
        if not type:
            self.conn.commit()
        self.conn.close()

class Item:
    def __init__(self, id, title, emojis, quantity, checked):
        self.id = id
        self.title = title
        self.emojis = emojis
        self.quantity = quantity
        self.checked = checked

    @classmethod
    def from_db(cls, row):
        item = cls(id=row['id'], title=row['title'], emojis=row['emojis'], quantity=row['quantity'], checked=row['checked'] != 0)
        return item

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'emojis': self.emojis,
            'quantity': self.quantity,
            'checked': self.checked,
        }

    def update(self, id, title=None, emojis=None, quantity=None, checked=None):
        assert self.id == id
        if quantity is not None and self.quantity != quantity:
            quantity = max(0, quantity)
            if quantity == 0:
                self.checked = True
            else:
                self.checked = False
        if checked is not None and self.checked != checked:
            if checked:
                self.quantity = 0
            else:
                self.quantity = 1
        if title is not None:
            self.title = title
        if emojis is not None:
            self.emojis = emojis
        if quantity is not None:
            self.quantity = quantity
        if checked is not None:
            self.checked = checked

    @staticmethod
    def split_title(title):
        emoji_regex = re.compile("["
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251"
            "]")
        emojis = emoji_regex.findall(title)
        emojis = ''.join(emojis)
        title = emoji_regex.sub('', title)
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) == 0:
            return
        return {
            'title': title,
            'emojis': emojis,
        }

class Logger:
    def __init__(self, method):
        self.method = method
        self.logged = 0
        self.items = []
        self.exception = None

    def __enter__(self):
        return self

    def log_item(self, item):
        self.items.append(item)

    def log_exception(self, exception):
        assert self.exception is None
        self.exception = exception

    def __exit__(self, type, value, traceback):
        data = flask.request.data.decode('utf8')
        ip = flask.request.environ.get('HTTP_X_FORWARDED_FOR', flask.request.remote_addr)
        user_agent = flask.request.headers.get('User-Agent')
        try:
            data_json = json.loads(data)
            lat = data_json['lat']
            lng = data_json['lng']
        except:
            lat = 0
            lng = 0

        with DB(DB_FILENAME) as db:
            if type is not None:
                params = (ip, user_agent, lat, lng, self.method, data, str(value))
                db.conn.execute('insert into log (timestamp, ip, user_agent, lat, lng, method, data, exception) values (current_timestamp,?,?,?,?,?,?,?)', params)
                return

            if self.exception is not None:
                params = (ip, user_agent, lat, lng, self.method, data, str(self.exception))
                db.conn.execute('insert into log (timestamp, ip, user_agent, lat, lng, method, data, exception) values (current_timestamp,?,?,?,?,?,?,?)', params)
                return

            for item in self.items:
                params = (ip, user_agent, lat, lng, self.method, data, item.id, item.title, item.emojis, item.quantity, item.checked)
                db.conn.execute('insert into log (timestamp, ip, user_agent, lat, lng, method, data, item_id, title, emojis, quantity, checked) values (current_timestamp,?,?,?,?,?,?,?,?,?,?,?)', params)

@app.route('/')
def redir_index():
    if 'X-Forwarded-Server' in flask.request.headers:
        return flask.redirect('http://www.pcfocus.gr/s/index.html', 302)
    else:
        return flask.redirect('http://%s/index.html' % flask.request.host, 302)

@app.route('/index.html')
def index():
    return flask.send_from_directory('', 'index.html')

@app.route('/data.json')
def data():
    ret = {
        'items': [],
    }
    with DB(DB_FILENAME) as db:
        for row in db.conn.execute('select * from items'):
            ret['items'].append(Item.from_db(row).to_dict())
    return ret

@app.route('/new', methods=['POST'])
def new():
    with Logger('new') as logger, DB(DB_FILENAME) as db:
        data = json.loads(flask.request.data)
        del data['lat']
        del data['lng']
        p = Item.split_title(data['title'])
        if p is None:
            logger.log_exception('split_title failed')
            return json.dumps(False)
        cursor = db.conn.cursor()
        try:
            existing = cursor.execute('select * from items where title=? collate nocase', (p['title'],)).fetchone()
            if existing is not None:
                item = Item.from_db(existing)
                item.update(id=item.id, checked=False)
                params = (item.quantity, item.checked, item.id)
                db.conn.execute('update items set quantity=?, checked=? where id=?', params)
            else:
                item = Item(**p, id=None, quantity=1, checked=False)
                params = (item.title, item.emojis, item.quantity, item.checked)
                cursor.execute('insert into items (title, emojis, quantity, checked) values (?,?,?,?)', params)
                item.id = cursor.lastrowid
            logger.log_item(item)
            return item.to_dict()
        except Exception as e:
            logger.log_exception(e)
            return json.dumps(False)

@app.route('/update', methods=['POST'])
def update():
    ret = []
    with Logger('update') as logger, DB(DB_FILENAME) as db:
        data = json.loads(flask.request.data)
        del data['lat']
        del data['lng']
        for item_dict in data['items']:
            if 'title' in item_dict:
                p = Item.split_title(item_dict['title'])
                if p is None:
                    logger.log_exception('split_title failed')
                    return json.dumps(False)
                del item_dict['title']
            else:
                p = {}
            row = db.conn.execute('select * from items where id=?', (item_dict['id'],)).fetchone()
            item = Item.from_db(row)
            item.update(**p, **item_dict)
            params = (item.title, item.emojis, item.quantity, item.checked, item.id)
            db.conn.execute('update items set title=?, emojis=?, quantity=?, checked=? where id=?', params)
            logger.log_item(item)
            ret.append(item.to_dict())
    return json.dumps(ret)

@app.route('/delete', methods=['POST'])
def delete():
    with Logger('delete') as logger, DB(DB_FILENAME) as db:
        data = json.loads(flask.request.data)
        del data['lat']
        del data['lng']
        item_id = data['id']
        logger.log_item(Item(id=item_id, title=None, emojis=None, quantity=None, checked=None))
        db.conn.execute('delete from items where id=?', (item_id,))
    return json.dumps(True)

def main():
    app.run()

if __name__ == '__main__':
    main()
