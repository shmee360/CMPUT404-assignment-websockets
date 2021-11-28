#!/usr/bin/env python
# coding: utf-8
# Copyright (c) 2013-2014 Abram Hindle
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Modifications copyright © 2021 Warren Stix
#

import flask
from flask import Flask, request, redirect
from flask_sockets import Sockets
import gevent
from gevent import queue
import json

app = Flask(__name__)
sockets = Sockets(app)
app.debug = True

class World:
    def __init__(self):
        self.clear()
        # we've got listeners now!
        self.listeners = list()
        
    def add_set_listener(self, listener):
        self.listeners.append( listener )

    def update(self, entity, key, value):
        entry = self.space.get(entity,dict())
        entry[key] = value
        self.space[entity] = entry
        self.update_listeners( entity )

    def set(self, entity, data):
        self.space[entity] = data
        self.update_listeners( entity )

    def update_listeners(self, entity):
        '''update the set listeners'''
        for listener in self.listeners:
            listener(entity, self.get(entity))

    def clear(self):
        self.space = dict()

    def get(self, entity):
        return self.space.get(entity,dict())
    
    def world(self):
        return self.space


myWorld = World()        


# Client class and related code from:
#  https://raw.githubusercontent.com/abramhindle/WebSocketsExamples/master/chat.py
# Gotta handle that producer-consumer problem!
class Client:
    def __init__(self):
        self.queue = queue.Queue()

    def put(self, v):
        self.queue.put_nowait(v)

    def get(self):
        return self.queue.get()


@app.route('/')
def hello():
    return redirect('/static/index.html')

def read_ws(ws):
    '''A greenlet function that reads from the websocket and updates the world'''
    try:
        # send the existing world
        ws.send(json.dumps(myWorld.world()))

        while True:
            msg = ws.receive()

            if msg is not None:
                change = json.loads(msg)
                for k, v in change.items():
                    myWorld.set(k, v)
            else:
                break
    except Exception as e:
        print('Error:', e)

@sockets.route('/subscribe')
def subscribe_socket(ws):
    '''Fufill the websocket URL of /subscribe, every update notify the
       websocket and read updates from the websocket '''
    client = Client()

    def listener(entity, data):
        packet = json.dumps({ entity: data })
        client.put(packet)

    myWorld.add_set_listener(listener)

    g = gevent.spawn(read_ws, ws)

    try:
        while True:
            msg = client.get()
            ws.send(msg)
    except Exception as e:
        print('Websocket Error:', e)
    finally:
        myWorld.listeners.remove(listener)
        gevent.kill(g)

    return flask.jsonify(dict())


# I give this to you, this is how you get the raw body/data portion of a post in flask
# this should come with flask but whatever, it's not my project.
def flask_post_json():
    '''Ah the joys of frameworks! They do so much work for you
       that they get in the way of sane operation!'''
    if (request.json != None):
        return request.json
    elif (request.data != None and request.data.decode("utf8") != u''):
        return json.loads(request.data.decode("utf8"))
    else:
        return json.loads(request.form.keys()[0])

@app.route("/entity/<entity>", methods=['POST','PUT'])
def update(entity):
    '''update the entities via this interface'''
    data = flask_post_json()[entity]
    myWorld.set(entity, data)

    return json.dumps({ entity: myWorld.get(entity) })

@app.route("/world", methods=['POST','GET'])    
def world():
    return json.dumps(myWorld.world())

@app.route("/entity/<entity>")    
def get_entity(entity):
    data = myWorld.get(entity)

    return flask.jsonify(data)


@app.route("/clear", methods=['POST','GET'])
def clear():
    '''Clear the world out!'''
    myWorld.clear()

    return flask.jsonify(dict())


if __name__ == "__main__":
    ''' This doesn't work well anymore:
        pip install gunicorn
        and run
        gunicorn -k flask_sockets.worker sockets:app
    '''
    app.run()
