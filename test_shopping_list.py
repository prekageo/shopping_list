#!/usr/bin/env python3

import json
import pytest
import sqlite3

import shopping_list

@pytest.fixture
def client():
    shopping_list.DB_FILENAME = 'file::memory:?cache=shared'
    shopping_list.app.config['TESTING'] = True
    with shopping_list.app.test_client() as client:
        yield client

@pytest.fixture
def db_conn():
    with sqlite3.connect(shopping_list.DB_FILENAME, uri=True) as conn:
        conn.execute('drop table if exists items')
        conn.execute('drop table if exists log')
        conn.row_factory = sqlite3.Row
        yield conn

################################################################################

def test_empty(client):
    rv = client.get('/data.json')
    assert json.loads(rv.data) == {'items': []}

def test_update_invalid(client, db_conn):
    with pytest.raises(json.decoder.JSONDecodeError):
        client.post('/update')

    items, logs = get_items_logs(db_conn)
    assert len(items) == 0
    assert len(logs) == 1
    assert_log(logs[0], 'update', '', 'Expecting value: line 1 column 1 (char 0)')

def test_update_non_existent(client, db_conn):
    data = json.dumps({'items':[{'id':42, 'title':'foo'}], 'lat':0, 'lng':0})
    with pytest.raises(TypeError):
        client.post('/update', data=data)

    items, logs = get_items_logs(db_conn)
    assert len(items) == 0
    assert len(logs) == 1
    assert_log(logs[0], 'update', data, "'NoneType' object is not subscriptable")

def test_delete_non_existent(client, db_conn):
    data = json.dumps({'id':42, 'lat':0, 'lng':0})
    rv = client.post('/delete', data=data)
    assert json.loads(rv.data) == True

    items, logs = get_items_logs(db_conn)
    assert len(items) == 0
    assert len(logs) == 1
    assert_log(logs[0], 'delete', data, None)
    assert logs[0]['item_id'] == 42

def test_new(client, db_conn):
    data = json.dumps({'title':'eggs✅', 'lat':0, 'lng':0})
    rv = client.post('/new', data=data)
    item = dict(id=1, title='eggs', emojis='✅', checked=False, quantity=1)
    assert json.loads(rv.data) == item
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 1
    assert_log(logs[0], 'new', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[0][k if k != 'id' else 'item_id'] == v

def test_new_empty(client, db_conn):
    data = json.dumps({'title':'✅', 'lat':0, 'lng':0})
    rv = client.post('/new', data=data)
    assert json.loads(rv.data) == False
    items, logs = get_items_logs(db_conn)
    assert len(items) == 0
    assert len(logs) == 1
    assert_log(logs[0], 'new', data, 'split_title failed')

def test_new_duplicate_checked(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    client.post('/update', data=json.dumps({'items':[{'id':1, 'checked': True}], 'lat':0, 'lng':0}))
    data = json.dumps({'title':'EGGs  ', 'lat':0, 'lng':0})
    rv = client.post('/new', data=data)
    item = dict(id=1, title='eggs', emojis='', checked=False, quantity=1)
    assert json.loads(rv.data) == item
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 3
    assert_log(logs[2], 'new', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[2][k if k != 'id' else 'item_id'] == v

def test_new_duplicate_unchecked(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'title':'eggs  ', 'lat':0, 'lng':0})
    rv = client.post('/new', data=data)
    item = dict(id=1, title='eggs', emojis='', checked=False, quantity=1)
    assert json.loads(rv.data) == item
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 2
    assert_log(logs[1], 'new', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[1][k if k != 'id' else 'item_id'] == v

def test_update(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'items':[{'id': 1, 'title':'eggs2✅'}], 'lat':0, 'lng':0})
    rv = client.post('/update', data=data)
    item = dict(id=1, title='eggs2', emojis='✅', checked=False, quantity=1)
    assert json.loads(rv.data) == [item]
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 2
    assert_log(logs[1], 'update', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[1][k if k != 'id' else 'item_id'] == v

def test_update_quantity(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'items':[{'id': 1, 'quantity':2}], 'lat':0, 'lng':0})
    rv = client.post('/update', data=data)
    item = dict(id=1, title='eggs', emojis='', checked=False, quantity=2)
    assert json.loads(rv.data) == [item]
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 2
    assert_log(logs[1], 'update', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[1][k if k != 'id' else 'item_id'] == v

def test_update_duplicate(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    client.post('/new', data=json.dumps({'title':'milk', 'lat':0, 'lng':0}))
    data = json.dumps({'items':[{'id': 1, 'title':'milk✅'}], 'lat':0, 'lng':0})
    with pytest.raises(sqlite3.IntegrityError):
        client.post('/update', data=data)
    items, logs = get_items_logs(db_conn)
    assert len(items) == 2
    assert len(logs) == 3
    assert_log(logs[2], 'update', data, 'UNIQUE constraint failed: items.title')

def test_update_same_title(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'items':[{'id': 1, 'title':'  eggs  '}], 'lat':0, 'lng':0})
    rv = client.post('/update', data=data)
    item = dict(id=1, title='eggs', emojis='', checked=False, quantity=1)
    assert json.loads(rv.data) == [item]
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 2
    assert_log(logs[1], 'update', data, None)
    for k, v in item.items():
        assert items[0][k] == v
        assert logs[1][k if k != 'id' else 'item_id'] == v

def test_update_empty(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'items':[{'id': 1, 'title':'✅'}], 'lat':0, 'lng':0})
    rv = client.post('/update', data=data)
    assert json.loads(rv.data) == False
    items, logs = get_items_logs(db_conn)
    assert len(items) == 1
    assert len(logs) == 2
    assert_log(logs[1], 'update', data, 'split_title failed')

def test_update_multiple(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    client.post('/new', data=json.dumps({'title':'milk', 'lat':0, 'lng':0}))
    data = json.dumps({'lat':0, 'lng':0, 'items':[
        {'id': 1, 'title':'eggs2'},
        {'id': 2, 'title':'milk2'},
    ]})
    rv = client.post('/update', data=data)
    expected_items = [
        dict(id=1, title='eggs2', emojis='', checked=False, quantity=1),
        dict(id=2, title='milk2', emojis='', checked=False, quantity=1),
    ]
    assert json.loads(rv.data) == expected_items
    items, logs = get_items_logs(db_conn)
    assert len(items) == 2
    assert len(logs) == 4
    for i, item in enumerate(expected_items):
        for k, v in item.items():
            assert items[i][k] == v
            assert logs[2+i][k if k != 'id' else 'item_id'] == v

def test_delete(client, db_conn):
    client.post('/new', data=json.dumps({'title':'eggs', 'lat':0, 'lng':0}))
    data = json.dumps({'id': 1, 'lat':0, 'lng':0})
    rv = client.post('/delete', data=data)
    assert json.loads(rv.data) == True
    items, logs = get_items_logs(db_conn)
    assert len(items) == 0
    assert len(logs) == 2
    assert_log(logs[1], 'delete', data, None)
    assert logs[1]['item_id'] == 1

################################################################################

def test_item_update():
    attribs = dict(title='title', emojis='emojis', quantity=42, checked=False)

    item = shopping_list.Item(id=1, **attribs)
    with pytest.raises(AssertionError):
        item.update(id=2)

    item.update(id=1)
    for k, v in attribs.items():
        assert getattr(item, k) == v

    for k2 in 'title', 'emojis':
        item = shopping_list.Item(id=1, **attribs)
        item.update(id=1, **{k2: 'new'})
        for k, v in attribs.items():
            if k == k2:
                assert getattr(item, k) == 'new'
            else:
                assert getattr(item, k) == v

    item = shopping_list.Item(id=1, **attribs)
    item.update(id=1, quantity=43)
    for k, v in attribs.items():
        if k == 'quantity':
            assert getattr(item, k) == 43
        else:
            assert getattr(item, k) == v

def test_item_update_checked_quantity():
    attribs = dict(title='title', emojis='emojis')

    item = shopping_list.Item(id=1, quantity=42, checked=False, **attribs)
    item.update(id=1, checked=True)
    assert item.quantity == 0
    assert item.checked == True
    for k, v in attribs.items():
        assert getattr(item, k) == v

    item = shopping_list.Item(id=1, quantity=42, checked=False, **attribs)
    item.update(id=1, quantity=0)
    assert item.quantity == 0
    assert item.checked == True
    for k, v in attribs.items():
        assert getattr(item, k) == v

    item = shopping_list.Item(id=1, quantity=0, checked=True, **attribs)
    item.update(id=1, quantity=42)
    assert item.quantity == 42
    assert item.checked == False
    for k, v in attribs.items():
        assert getattr(item, k) == v

    item = shopping_list.Item(id=1, quantity=0, checked=True, **attribs)
    item.update(id=1, checked=False)
    assert item.quantity == 1
    assert item.checked == False
    for k, v in attribs.items():
        assert getattr(item, k) == v

def test_item_split_title():
    assert shopping_list.Item.split_title('') is None
    expected = {'title': 'eggs', 'emojis': ''}
    assert shopping_list.Item.split_title('eggs') == expected
    assert shopping_list.Item.split_title('   eggs') == expected
    assert shopping_list.Item.split_title('  eggs    ') == expected
    assert shopping_list.Item.split_title('eggs  ') == expected
    assert shopping_list.Item.split_title('  word1   word2  word3 ') == {'title': 'word1 word2 word3', 'emojis': ''}

    assert shopping_list.Item.split_title('  ✂  word1   word2  ✅ ') == {'title': 'word1 word2', 'emojis': '✂✅'}
    assert shopping_list.Item.split_title('    word1   ✅ ') == {'title': 'word1', 'emojis': '✅'}

    assert shopping_list.Item.split_title('eggs🥚') == {'title': 'eggs', 'emojis': '🥚'}

################################################################################

def get_items_logs(db_conn):
    items = db_conn.execute('select * from items').fetchall()
    logs = db_conn.execute('select * from log').fetchall()
    return items, logs

def assert_log(log, method, data, exception):
    assert log['data'] == data
    assert log['exception'] == exception
    assert log['method'] == method
    assert log['ip'] == '127.0.0.1'
    assert log['user_agent'] == 'werkzeug/1.0.1'
