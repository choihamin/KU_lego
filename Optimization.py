import math
import os
import urllib.parse as up
import psycopg2, datetime
from flask import Flask, render_template, request, redirect, session, jsonify
from flask_restx import Api, Resource
from mapboxgl.utils import df_to_geojson
import json
import numpy as np
import logging
import pandas as pd
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

def make_data(n):
    master = []
    for i in range(n):
        mat_weekday = []
        for i in range(5):
            tmp = []
            for i in range(2):
                a = list(np.random.poisson(lam=(1984/820)/6.3, size = 12))
                val = sum(a)
                b = list(np.random.poisson(1/3, 3))
                c = [0]*3
                c[b.index(max(b))] = val
                d = [0]*6 + c + [0]*3
                tmp += d
            mat_weekday.append(tmp)
        mat_weekday = np.array(mat_weekday)

        mat_weekend = []
        for i in range(2):
            tmp = []

            a = list(np.random.poisson(lam=(1984/540)/6.3, size = 12))
            val = sum(a)
            b = list(np.random.poisson(1/8, 8))
            c = [0]*8
            c[b.index(max(b))] = val
            d = [0]*6 + c
            tmp += d

            a = list(np.random.poisson(lam=(1984/540)/6.3, size = 12))
            val = sum(a)
            b = list(np.random.poisson(1/10, 10))
            c = [0]*10
            c[b.index(max(b))] = val
            tmp += c
            mat_weekend.append(tmp)
        mat_weekend = np.array(mat_weekend)

        mat = np.vstack((mat_weekday, mat_weekend)).flatten()
        master.append(mat)
    master = np.array(master).T
    return master

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

        cur.execute("insert into CusDriver values('{}','{}')".format(id, 'driver'))
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
    cur.execute("select customer_name, car_model_name, battery_capacity, efficiency, car_number from (Customer natural join CusSpec) natural join CarModel where customer_id='{}'".format(id))
    data = cur.fetchall()

    if len(data) == 0:
        cur.execute("select customer_name from Customer where customer_id='{}'".format(id))
        data = cur.fetchall()
        name = data[0][0]
        car_model = "정보없음"
        battery_capacity = "정보없음"  # 차량 배터리용량
        efficiency = "정보없음"  # 연비
        current_capacity = "정보없음"
        car_number = "정보없음"

    else:
        name = data[0][0]
        car_model = data[0][1]
        battery_capacity = data[0][2] # 차량 배터리용량
        efficiency = data[0][3]       # 연비
        current_capacity = 45
        car_number = data[0][4]
    connect.close()



    return jsonify({'name': name,
                    'car_model_name': car_model,
                    'efficiency': efficiency,
                    'battery_capacity': battery_capacity,
                    'current_capacity': current_capacity,
                    'car_number': car_number
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

    customer_id = request.args.get("Id")
    car_model_id = request.args.get('Car_model_id')
    car_number = request.args.get('Car_number')
    prefer_time = request.args.get('Time_type')
    prefer_battery = request.args.get('Prefer_battery')

    station1 = request.args.get('Station_0')
    station2 = request.args.get('Station_1')
    station3 = request.args.get('Station_2')

    try:
        cur.execute("insert into CarCus values('{}',{})".format(customer_id, car_model_id))
        connect.commit()

        cur.execute("insert into CusSpec values('{}', {}, '{}')".format(customer_id, car_model_id, car_number))
        connect.commit()

        cur.execute("insert into PreferTime values('{}', {}, {})".format(customer_id, prefer_time, prefer_battery))
        connect.commit()

        cur.execute(
            "insert into PreferStation values('{}', {}, {}, {})".format(customer_id, station1, station2, station3))
        connect.commit()
        print('오예')

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



@app.route('/SetChargeCompleteInfo', methods=['GET', 'POST'])
def SetChargeCompleteInfo():

    connect = conn()
    cur = connect.cursor()
    id = request.args.get('Id')
    complete_time = request.args.get('Complete_time')

    print(complete_time)




    cur.execute("select datetime, energy_consumption from Consumption where customer_id='{}'".format(id))
    data = cur.fetchall()

    ### 배터리 잔량 비울 ###
    cur.execute("select prefer_battery, time_type from PreferTime where customer_id='{}'".format(id))
    preferTime = cur.fetchall()
    C = int(preferTime[0][0])/100
    prefer_time = int(preferTime[0][1])

    print(prefer_time)
    #####################

    ### 연비############
    cur.execute("select efficiency from CarCus natural join CarModel where customer_id='{}'".format(id))
    w = cur.fetchall()[0][0]
    ####################

    ### 배터리 ##########
    cur.execute("select battery_capacity from CarCus natural join CarModel where customer_id='{}'".format(id))
    B = float(cur.fetchall()[0][0])
    ####################


    try:
        data = sorted(data, key=lambda x: x[0])
        data = np.array(list(map(lambda x: x[1], data)))

        #### 데이터 수 = 0 ############################### 임시변통
        if len(data) == 0:
            a = make_data(7)
            flat = a.T.flatten()
            total_hours = len(flat)

            now = datetime.datetime.now()
            for i in range(total_hours):
                timeline = (now - datetime.timedelta(hours= total_hours - i)).strftime("%Y-%m-%d %H:%M:%S")
                cur.execute("insert into Consumption values('{}', '{}', {})".format(id, timeline, float(flat[i])))
                connect.commit()

            cur.execute("select datetime, energy_consumption from Consumption where customer_id='{}'".format(id))
            data = cur.fetchall()

        #### 데이터 수 > 168 #############################
        if len(data) >= 168:
            if len(data) % 168 != 0:
                data = data[:-(data % 168)]
            data = data.reshape(-1, 168).T

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
            globals()['delta_b%d'%i] = result[i]
        ###########################################

        obj = t0
        for i in range(1, len(result)):
            obj += globals()['t%d' % i]
        m.setObjective(obj, GRB.MAXIMIZE)

        const = delta_b0 * t0
        for i in range(1, len(result)):
            const += globals()['delta_b%d' % i] * globals()['t%d' % i]

        m.addConstr(B - const >= B * C, name='c0')

        const = t0
        for i in range(1, len(result)):
            const += globals()['t%d' % i]
        m.addConstr(const >= 1, name='c1')

        for i in range(len(result) - 1):
            m.addConstr(globals()['t%d' % i] >= globals()['t%d' % (i + 1)])
        m.optimize()

        last_Charging_Time = 10
        free_time = 2

        current = datetime.datetime.strptime(complete_time, "%Y-%m-%d %H:%M:%S")
        min_battery_time = current + datetime.timedelta(hours=m.ObjVal)
        recommend_time = min_battery_time - datetime.timedelta(hours=24)

        Y = recommend_time.year
        m = recommend_time.month
        d = recommend_time.day
        H = prefer_time
        M = recommend_time.minute
        S = recommend_time.second

        min_battery_time = datetime.datetime.strftime(min_battery_time, "%Y-%m-%d %H:%M:%S")
        recommend_time = datetime.datetime.strftime(datetime.datetime(Y, m, d, H, M, S), "%Y-%m-%d %H:%M:%S")

        print(min_battery_time, recommend_time)

        cur.execute("insert into Schedule values('{}','{}','{}','{}')".format(id, complete_time, min_battery_time, recommend_time))
        connect.commit()

        return jsonify({'result_code': 1})
    except Exception as e:
        print(e)
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetScheduleInfo', methods=['GET', 'POST'])
def GetScheduleInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')

    min_battery_time = '정보없음'
    charge_time = '정보없음'
    prefer_battery = '정보없음'


    try:

        cur.execute("select complete_time, min_battery_time, charge_time from Schedule where customer_id='{}'".format(id))
        data = cur.fetchall()

        print(data)

        cur.execute("select prefer_battery from PreferTime where customer_id='{}'".format(id))
        prefer_battery = cur.fetchall()[0][0]
        print(prefer_battery)

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

@app.route('/SetSubInfo', methods=['GET', 'POST'])
def SetSubInfo():
    connect = conn()
    cur = connect.cursor()

    id = request.args.get('Id')
    reserve_time = request.args.get('Reserve_time')
    location = request.args.get('Location')
    notice = request.args.get('Notice')

    cur.execute("select reserve_id from Substitute")
    reserve_id_lst = cur.fetchall()
    if len(reserve_id_lst) != 0:
        reserve_id = max(list(map(lambda x: x[0], reserve_id_lst))) + 1
    else:
        reserve_id = 0

    try:
        cur.execute("select * from Substitute where customer_id='{}' and reserve_time='{}' and location='{}'".format(id,
                                                                                                                     reserve_time,
                                                                                                                     location))
        if len(cur.fetchall()) != 0:
            raise Exception
        cur.execute("insert into Substitute values({},'{}', '{}', '{}', '{}')".format(reserve_id,
                                                                                      id,
                                                                                      location,
                                                                                      reserve_time,
                                                                                      notice))
        connect.commit()

        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetSubInfo', methods=['GET', 'POST'])
def GetSubInfo():
    connect = conn()
    cur = connect.cursor()
    id = request.args.get('Id')

    try:
        sql = "select reserve_id, reserve_time, location, notice, driver_name, driver_phone, pick_up_time, Complete_time from Substitute natural join (CusDriver natural join Driver) where customer_id = '{}'"
        cur.execute(sql.format(id))
        data = cur.fetchall()
        target = sorted(data, key=lambda x: x[2])[-1]
        print(target)

        reserve_id = target[0]
        reserve_time = target[1]
        location = target[2]
        notice = target[3]
        driver_name = target[4]
        driver_phone = target[5]
        pick_up_time = target[6]
        complete_time = target[7]

        return jsonify({'reserve_id': reserve_id,
                        'reserve_time': reserve_time,
                        'location': location,
                        'notice': notice,
                        'driver_name': driver_name,
                        'driver_phone': driver_phone,
                        'pick_up_time': pick_up_time,
                        'complete_time': complete_time,
                        'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/GetDriverHomeInfo', methods=['GET', 'POST'])
def GetDriverHomeInfo():
    connect = conn()
    cur = connect.cursor()
    driver_id = request.args.get('Id')

    try:
        sql = "select reserve_id, reserve_time, location, customer_name, phone, car_number, car_model_name, notice from (((cusspec natural join carmodel) natural join substitute) natural join customer) natural join cusdriver where driver_id = '{}'"
        cur.execute(sql.format(driver_id))
        data = cur.fetchall()
        data = sorted(data, key = lambda x: x[1])

        return jsonify(list=[dict(reserve_id=data[i][0], reserve_time=data[i][1], location=data[i][2],
                                  customer_name=data[i][3], customer_phone=data[i][4], car_number=data[i][5],
                                  car_model_name=data[i][6], notice=data[i][7]) for i in range(len(data))])
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()


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

@app.route('/SetPickUpInfo', methods=['GET', 'POST'])
def SetPickUpInfo():
    connect = conn()
    cur = connect.cursor()

    reservation_id = request.args.get('Reservation_id')
    pick_up_time = request.args.get('Pick_up_time')

    try:
        cur.execute("update Substitute set pick_up_time = '{}' where reserve_id='{}'".format(pick_up_time, reservation_id))
        connect.commit()
        return jsonify({'result_code': 1})
    except:
        return jsonify({'result_code': 0})
    finally:
        if connect is not None:
            connect.close()

@app.route('/SetSubCompleteInfo', methods=['GET', 'POST'])
def SetSubCompleteInfo():
    connect = conn()
    cur = connect.cursor()

    reservation_id = request.args.get('Reservation_id')
    complete_time = request.args.get('Complete_time')

    try:
        cur.execute("update Substitute set complete_time = '{}' where reserve_id={}".format(complete_time, reservation_id))
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port='5001', debug=True)











