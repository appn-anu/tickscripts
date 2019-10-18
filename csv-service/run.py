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
        rawdata = self.request.recv(1024).strip()
        output_dir = os.getenv("OUTPUT_DIR")
        try:
            data = json.loads(rawdata)
        except Exception as e:
            data = None
            print(e)
            return
        if data is None:
            print("data is None, wtf")
            return

        print("Recieved csv json {}".format(data))

        os.makedirs(os.path.join("/data/", output_dir), exist_ok=True)
        for series in data['data']['series']:
            header = ",".join(series['columns'])
            pathname = "{}_{}.csv.gz".format((datetime.datetime.now()-datetime.timedelta(hours=24)).strftime("%Y-%m-%d"),series['name'])
            with gzip.open(os.path.join("/data/", output_dir, pathname), 'wt') as f:
                f.write(header+"\n")
                for tp in series['values']:
                    f.write(",".join([str(x) for x in tp])+"\n")

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


