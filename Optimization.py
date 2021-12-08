import math
import os
import urllib.parse as up
import psycopg2, datetime
from flask import Flask, render_template, request, redirect, session, jsonify
from flask_restx import Api, Resource
from mapboxgl.utils import df_to_geojson
import json
import numpy as np
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
import gurobipy as gp
from gurobipy import GRB

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

@app.route('/CheckLogin', methods=['GET', 'POST'])
def CheckLogin():
    connect = conn()
    cur = connect.cursor()
    id = request.args.get('Id')
    pw = request.args.get('Password')
    cur.execute("select * from customer where customer_id='{}' and password='{}'".format(id, pw))
    data = cur.fetchall()

    if len(data) == 1:
        connect.close()
        return jsonify({'result_code': 1})
    else:
        cur.execute("select * from Driver where driver_id = '{}' and password='{}'".format(id, pw))
        data = cur.fetchall()
        if len(data) == 1:
            connect.close()
            return jsonify({'result_code': 2})
        else:
            connect.close()
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
    phone = request.args.get('Phone')
    try:
        cur.execute("insert into customer values('{}','{}','{}','{}')".format(id, pw, name, phone))
        connect.commit()
        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetCarCompanyInfo', methods=['GET','POST'])
def GetCarCompanyInfo():
    connect = conn()
    cur = connect.cursor()
    try:
        cur.execute("select distinct manufacturer from CarModel")
        data = cur.fetchall()
        dict_ = jsonify(manufacturers=[dict(manufacturer = data[i][0]) for i in range(len(data))])
        return dict_
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetCarModelInfo', methods=['GET', 'POST'])
def GetCarModelInfo():
    connect = conn()
    cur = connect.cursor()
    company = request.args.get('Car_company')
    cur.execute("select car_model_id, car_model_name from CarModel where manufacturer='{}'".format(company))
    data = cur.fetchall()
    dict_ = jsonify(models=[dict(model_id=data[i][0], model_name=data[i][1]) for i in range(len(data))])
    connect.close()
    return dict_

@app.route('/GetHomeInfo', methods=['GET', 'POST'])
def GetHomeInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')
    cur.execute("select customer_name, car_model_name, battery_capacity, efficiency from Customer natural join CarModel where customer_id='{}'".format(id))
    data = cur.fetchall()
    name = data[0][0]
    car_model = data[0][1]
    battery_capacity = data[0][2] # 차량 배터리용량
    efficiency = data[0][3]       # 연비
    current_capacity = 45
    connect.close()



    return jsonify({'name': name,
                        'car_model_name': car_model,
                        'efficiency': efficiency,
                        'battery_capacity': battery_capacity,
                        'current_capacity' : current_capacity
                        })

"""@app.route('/PredictDemand', methods=['GET', 'POST'])
def PredictDemand():
    connect = conn()
    cur = connect.cursor()
    cur.execute("select * from Record")
    data = cur.fetchall()

    number_of_station = len(set(list(map(lambda x: x[0], data))))
    number_of_time = 24
    station_number_list = set(list(map(lambda x: x[0], data)))

    Demand_matrix = [0 for i in range(number_of_time) for j in range(number_of_station)]

    for e in data:
        for i in range(24):
            if i < 10:
                interval = "0" + str(i)
            else:
                interval = str(i)
            for j in station_number_list:
                 if e[1][-2] == interval and e[0] == j:
                     Demand_matrix[j][i] += e[2]

    for i in range(len(Demand_matrix)):
        for j in range(len(Demand_matrix)):
            Demand_matrix[i][j] //= 7

    return Demand_matrix"""

@app.route('/SetCarInfo', methods=['GET','POST'])
def SetCarInfo():
    connect = conn()
    cur = connect.cursor()

    customer_id = request.args.get("Customer_id")
    car_model_id = request.args.get('Car_model_id')
    car_number = request.args.get('Car_number')
    prefer_time = request.args.get('Time_type')
    prefer_battery = request.args.get('Prefer_battery')

    station1 = request.args.get('Station_0')
    station2 = request.args.get('Station_1')
    station3 = request.args.get('Station_2')

    try:
        cur.execute("insert into CusSpec values('{}', {}, '{}')".format(customer_id, car_model_id, car_number))
        connect.commit()

        cur.execute("insert into PreferTime values('{}', {}, {})".format(customer_id, prefer_time, prefer_battery))
        connect.commit()

        cur.execute(
            "insert into PreferStation values('{}', {}, {}, {}".format(customer_id, station1, station2, station3))
        connect.commit()
        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

def weight_cal(data, r=1.1):
    n = data.shape[1]
    weight = [0]*n
    a = (r - 1)/(r**n-1)
    for i in range(n):
        weight[i] = a*r**i
    return np.array(weight)



@app.route('/SetChargeCompleteInfo')
def SetChargeCompleteInfo():

    connect = conn()
    cur = connect.cursor()
    id = request.args.get('ID')
    complete_time = request.args.get('Complete_time')

    cur.execute("select datetime, energy_consumption from Consumption where customer_id='{}'".format(id))
    data = cur.fetchall()

    ### 배터리 잔량 비울 ###
    cur.execute("select prefer_battery from PreferTime where customer_id='{}".format(id))
    C = cur.fetchall()[0]
    #####################

    ### 연비############
    cur.execute("select efficiency from CarCus natural join CarModel where customer_id='{}'".format(id))
    w = cur.fetchall()[0]
    ####################

    ### 배터리 ##########
    cur.execute("select battery_capacity from CarCus natural join CarModel where customer_id='{}'".format(id))
    B = cur.fetchall()[0]
    ####################

    try:
        data = sorted(data, key=lambda x: x[0])
        data = np.array(list(map(lambda x: x[1], data)))

        #### 데이터 수 > 168 #############################
        if len(data) >= 168:
            data = data.reshape(168, -1)
        #### 데이터 수 < 168 #############################
        else:
            data = data.reshape(-1, 1)
        #### 지수평활 알고리즘 ############################
        weight = weight_cal(data)
        result = data @ weight
        ################################################

        #### Optimization Process ######################
        m = gp.Model("MILP")
        ### Time Line ####################################################
        for i in range(len(result)):
            globals()['t%d' % i] = m.addVar(vtype=GRB.BINARY, name="t%d" % i)
        ##################################################################

        ## 배터리 예측 사용량 ####################
        for i in range(len(result)):
            globals()['delta_b%d' % (i)] = result[i]
        ###########################################

        obj = t0
        for i in range(1, len(result)):
            obj += globals()['t%d' % i]
        m.setObjective(obj, GRB.MAXIMIZE)

        const = delta_b0 * t0
        for i in range(1, len(result)):
            const += globals()['delta_b%d' % i] * globals()['t%d' % i]
        m.addConstr(B - const >= B * C, "c0")

        const = t0
        for i in range(1, len(result)):
            const += globals()['t%d' % i]
        m.addConstr(const >= 1, "c1")

        for i in range(len(result) - 1):
            m.addConstr(globals()['t%d' % i] >= globals()['t%d' % (i + 1)])
        m.optimize()

        prefered_Time = 19
        last_Charging_Time = 10
        free_time = 2

        i = 0
        while True:
            bound = prefered_Time - last_Charging_Time + 24 * (i + 1) + free_time
            if m.ObjVal < bound:
                break;
            i += 1
        recommend = bound - 24

        cur.execute("insert into Schedule values('{}','{}','{}','{}')".format(id, complete_time, m.ObjVal, recommend))
        connect.commit()

        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetScheduleInfo')
def GetScheduleInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')

    min_battery_time = '정보없음'
    charge_time = '정보없음'
    prefer_battery = '정보없음'


    try:

        cur.execute("select complete_time, min_battery_time, charge_time from Schedule where id = '{}'".format(id))
        data = cur.fetchall()

        cur.execute("select prefer_battery from PreferTime where customer_id='{}".format(id))
        prefer_battery = cur.fetchall()[0]

        data = sorted(data, key=lambda x: x[0])

        target = data[-1]
        min_battery_time = target[1]
        charge_time = target[2]
        return jsonify({'min_battery_time': min_battery_time,
                        'charge_time': charge_time,
                        'prefer_battery': prefer_battery})
    except:
        return jsonify({'min_battery_time': min_battery_time,
                        'charge_time': charge_time,
                        'prefer_battery': prefer_battery})
    finally:
        if connect is not None:
            connect.close()

@app.route('/SetSubInfo')
def SetSubInfo():



@app.route('/DriverSetSignUpInfo', methods=['GET', 'POST'])
def DriverSetSignUpInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')
    pw = request.args.get('Password')
    name = request.args.get('Name')
    try:
        cur.execute("insert into drvier values('{}','{}','{}')".format(id, pw, name))
        connect.commit()
        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetMyPageInfo', methods=['GET', 'POST'])
def GetMyPageInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')
    sql = "select customer_name, phone, customer_id, car_model_name, car_number voucher_name, voucher_period, total_count, pay_date, count from ((Customer natural join CusSpec) natural join CarModel) natural join (CusVoucher natural join Voucher) where customer_id='{}'"
    cur.execute(sql.format(id))
    data = cur.fetchall()
    name = data[0][0]
    phone_number = data[0][1]
    customer_id = data[0][2]
    car_model_name = data[0][3]  # 연비
    car_number = data[0][4]
    voucher_name = data[0][5]
    voucher_period = data[0][6]
    total_count = data[0][7]
    pay_date = data[0][8]
    count = data[0][9]

    connect.close()
    return jsonify({'name': name,
                    'phone_number': phone_number,
                    'customer_id': customer_id,
                    'car_model_name': car_model_name,
                    'car_number': car_number,
                    'voucher_name': voucher_name,
                    'voucher_period': voucher_period,
                    'total_count': total_count,
                    'pay_date': pay_date,
                    'count': count
                    })


# @app.route('/ModifyMyInfo', methods=['GET', 'POST'])













