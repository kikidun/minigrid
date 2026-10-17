import sqlite3
import config
import requests 
import time

def sweep():
    return

if __name__ == "__main__":
    while True:
        should_sweep = False
        try:
            response = requests.get(config.API_URL + "/health", timeout=2)
            if response.status_code == 200:
                if response.json()["sweep_ok"]:
                    print("Healthy, sweep ok!")
                    should_sweep = True
                else:
                    print("Healthy, no sweep!") 
            elif response.status_code == 503:
                print("DB down!")
            else:
                print(f"Unexpected status code {response.status_code} received!")
        except requests.RequestException:
            print("Endpoint unreachable!")

        if should_sweep:
            print("Sweeping...")
            #sweep(con)
            time.sleep(10)
        else:
            time.sleep(10)
        #con = connect()

        #hit the health endpoint

        #open the atomic transaction

