import math
import os
import urllib.parse as up
import psycopg2, datetime
from flask import Flask, render_template, request, redirect, session, jsonify
from flask_restx import Api, Resource
from mapboxgl.utils import df_to_geojson
import json
import uuid
import logging, time
from apscheduler.schedulers.background import BackgroundScheduler
import requests, bs4
import urllib
import pandas as pd
from fbprophet import Prophet
from socket import timeout
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote_plus, unquote
from collections import deque

app = Flask(__name__)
logging = logging.getLogger(__name__)
app.config['JSON_AS_ASCII'] = False
api = Api(app)

up.uses_netloc.append("postgres")
os.environ["DATABASE_URL"] = "postgres://yadctsip:mvZ_FWEhIcFp4PCZMlzUtdZivUkj1IBG@arjuna.db.elephantsql.com/yadctsip"
url = up.urlparse(os.environ["DATABASE_URL"])

connect = None

def conn():
    connect = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)
    return connect

# 현재 전기차와 나 사이의 거리
@app.route('/Search', methods=['GET', 'POST'])
def Search():
    connect = conn()
    cur = connect.cursor()
    my_dx = 126.5702672
    my_dy = 33.2465421
    cur.execute("select station_id, station_name, dx, dy from station")
    data = cur.fetchall()

    if len(data) == 0:
        return -1
    else:
        charger_distance = dict()
        for e in data:
            charger_id = e[0]
            charger_name = e[1]
            charger_dx = e[2]
            charger_dy = e[3]
            charger_distance[charger_id] = math.sqrt(
                (abs(charger_dx - my_dx) * math.cos(charger_dy) * 6400 * 2 * math.pi / 360) ** 2 + (
                            111 * abs(charger_dy - my_dy)) ** 2)

        charger_distance
        candidate = list(filter(lambda x: charger_distance[x] < 1, charger_distance))
        df = list(filter(lambda x: x[0] in candidate, data))
        distance = []
        for e in charger_distance:
            if e in candidate:
                distance.append(charger_distance[e])
        lst = []
        for i in range(len(distance)):
            lst.append(tuple(list(df[i][0:]) + [distance[i]]))

        lst = sorted(lst, key=lambda x: x[3])
        lst[:2]

        return jsonify(
            station_set=[dict(station_id=e[0], station_name=e[1], dx=e[2], dy=e[3], distance=e[4]) for e in lst])

@app.route('/CheckLogin', methods=['GET', 'POST'])
def CheckLogin():
    connect = conn()
    cur = connect.cursor()
    id = request.args.get('Id')
    pw = request.args.get('Password')
    cur.execute("select * from customer where customer_id='{}' and password='{}'".format(id, pw))
    data = cur.fetchall()
    connect.close()
    if len(data) == 1:
        return jsonify({'result_code': 1})
    else:
        return jsonify({'result_code': 0})


@app.route('/GetStationInfo', methods=['GET', 'POST'])
def GetStationInfo():
    connect = conn()
    cur = connect.cursor()
    cur.execute("select station_id, station_name, slow_charger, fast_charger, dx, dy, v2g from Station")
    data = cur.fetchall()
    data = pd.DataFrame(data, columns=['station_id', 'station_name', 'slow_charger', 'fast_charger', 'dx', 'dy', 'v2g'])
    geo_data = df_to_geojson(
        df=data,
        properties=['station_id', 'station_name', 'slow_charger', 'fast_charger', 'v2g'],
        lat='dx',
        lon='dy',
        precision=5,
        filename='station.geojson'
    )
    path = 'station.geojson'
    with open(path) as f:
        data = json.loads(f.read())
    connect.close()

    return data

@app.route('/SetSignUpInfo', methods=['GET', 'POST'])
def SetSignUpInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')
    pw = request.args.get('Password')
    name = request.args.get('Name')
    car_model = request.args.get('Car_model')
    prefer_time = request.args.get('Prefer_time')
    prefer_station1 = request.args.get('Prefer_station')
    prefer_station2 = request.args.get('Prefer_station')
    prefer_station3 = request.args.get('Prefer_station')

    try:
        cur.execute("insert into customer values('{}','{}','{}',{})".format(id, pw, name, int(car_model)))
        cur.execute("insert into PreferTime values('{}','{}')".format(id, prefer_time))
        cur.execute("insert into PreferStation values('{}','{}','{}',{})".format(id, prefer_station1, prefer_station2, prefer_station3))
        connect.commit()
        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()