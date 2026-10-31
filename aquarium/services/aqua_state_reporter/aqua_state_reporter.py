import Adafruit_DHT
import urllib.request,json, re,datetime,time

class Getter():
    def __init__(self):
        self.water_temperature_pattern = re.compile("^.* t=(?P<t>-?\d+)")

    def get_water_temperature(self):
        with open("/sys/bus/w1/devices/28-3c01d607c85d/w1_slave", "r") as file:
            # こんな感じで値が入っているはず↓
            # cd 01 55 05 7f a5 81 66 2f : crc=2f YES
            # cd 01 55 05 7f a5 81 66 2f t=28812
            lines = file.readlines()
            if len(lines) != 2:
                raise Exception("水温取得失敗 0行")
            match = self.water_temperature_pattern.match(lines[1])
            if match == None:
                raise Exception("水温取得失敗 正規表現不一致")
            wt = float(match.group("t"))
            if (wt == 0.0):
                raise Exception("水温取得失敗 値 0")
            return wt / 1000

    def get_temperature_and_humidity(self):
        sensor = Adafruit_DHT.AM2302
        pin = "14"
        humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
        if (humidity == None or temperature == None):
            raise Exception("湿度気温取得失敗")
        if (humidity > 100):
            raise Exception("湿度異常値検出")

        return float(humidity), float(temperature)

def report(dt, water_temperature, humidity, temperature):
    json_string =  json.dumps(
            {
                "timeStamp": f"{dt.year}-{dt.month:02}-{dt.day:02} {dt.hour:02}:{dt.minute:02}:{int(dt.second * 10 / 10):02}",
                "waterTemperature": water_temperature,
                "humidity": humidity,
                "temperature": temperature
            })
    try:
        request = urllib.request.Request(
            "http://dashboard-api.home-server.internal/api/aquarium-api/post-register-water-state",
            json_string.encode("utf-8"),
            {"Content-Type": "application/json"},
            method="POST")
        urllib.request.urlopen(request)
    except:
        print(json_string)
        raise Exception("HTTP通信エラー")


def main():
    getter = Getter()
    before = -1
    beforeWt = None
    beforeHumidity = None
    beforeTemperature = None
    retryFlag = False
    while True:
        dt = datetime.datetime.now()
        t = int(float(dt.second) / 10)
        if (t == before):
            time.sleep(1)
            continue
        try:
            wt = getter.get_water_temperature()
            humidity, temperature = getter.get_temperature_and_humidity()
            if((not retryFlag) and beforeWt != None and (abs(beforeWt - wt) > 5 or abs(beforeHumidity - humidity) > 5 or abs(beforeTemperature - temperature) > 5)):
                retryFlag = True
                time.sleep(1)
                continue
            report(dt,wt,humidity,temperature)
            before = t
            beforeWt = wt
            beforeHumidity = humidity
            beforeTemperature = temperature
            retryFlag = False
        except  Exception as e:
            print(e)
            time.sleep(1)

if __name__ == "__main__":
    main()