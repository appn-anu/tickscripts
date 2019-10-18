#!/usr/bin/env python3
import sys, os
import gzip
import datetime
import json
import time
import re
import socketserver

def datetime_decorator(func):
    def wrapped_func(*args, **kwargs):
        return func(datetime.datetime.now().isoformat(), " - ", *args, **kwargs)
    return wrapped_func

print = datetime_decorator(print)

class TCPCSVHandler(socketserver.BaseRequestHandler):
    def handle(self):


        buf_size = 2**12
        rawdata = ""
        while True:
            part = self.request.recv(buf_size)
            rawdata += part.decode('utf-8')
            if len(part) < buf_size:
                break
        try:
            data = json.loads(rawdata)
        except Exception as e:
            data = None
            print(e)
            return
        if data is None:
            print("data is None, wtf")
            return

        # print("Recieved csv json {}".format(data))
        total = 0
        os.makedirs("/data", exist_ok=True)
        
        for series in data['data']['series']:
            seriestotal = 0
            header = ",".join(series['columns'])
            pathname = "{}_{}.csv.gz".format((datetime.datetime.now()-datetime.timedelta(hours=24)).strftime("%Y-%m-%d"),series['name'])
            print("Writing points to {}".format(pathname))
            with gzip.open(os.path.join("/data/", pathname), 'wt') as f:
                f.write(header+"\n")
                for tp in series['values']:
                    f.write(",".join([str(x) for x in tp])+"\n")
                    total += 1
                    seriestotal +=1
            print(series['name'],"\t",seriestotal)
        print("total","\t\t",total)



def main():
    HOST,PORT = "0.0.0.0", 9999
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((HOST, PORT), TCPCSVHandler) as server:
        try:
            print("Started tcp csv server on {}:{}".format(HOST, PORT))
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server")
            server.server_close()
        except Exception as e:
            print("Unhandled fatal exception")
            print(e)
            server.server_close()

if __name__ == '__main__':
    main()


