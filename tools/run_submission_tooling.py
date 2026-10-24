"""Run actual Newman, Puppeteer and JMeter on an isolated local Flask server.

No public VPS load; no assertion result is invented or converted from Fail to Pass.
"""
import argparse
import csv
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import create_app, initialize
from werkzeug.serving import WSGIRequestHandler, make_server

TOOLING=ROOT/"submission"/"tooling"
EVIDENCE=ROOT/"submission"/"evidence"/"tooling"


class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):
        pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(command,log,env=None):
    began=time.monotonic()
    started=stamp()
    with log.open("w",encoding="utf-8") as stream:
        result=subprocess.run(command,cwd=TOOLING,env=env,stdout=stream,stderr=subprocess.STDOUT)
    return {"started":started,"finished":stamp(),"wall_seconds":round(time.monotonic()-began,3),"exit_code":result.returncode,"log":str(log.relative_to(ROOT))}


def percentile(values,p):
    if not values:return None
    values=sorted(values)
    return values[max(0,min(len(values)-1,__import__('math').ceil(p*len(values))-1))]


def jtl_metrics(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:records=list(csv.DictReader(stream))
    grouped=defaultdict(list)
    for row in records:grouped[row["label"]].append(row)
    metrics={}
    for label,rows in grouped.items():
        elapsed=[int(row["elapsed"]) for row in rows]
        span=(max(int(r["timeStamp"])+int(r["elapsed"]) for r in rows)-min(int(r["timeStamp"]) for r in rows))/1000
        metrics[label]={"samples":len(rows),"average_ms":round(sum(elapsed)/len(elapsed),3),"p90_ms":percentile(elapsed,.90),"p95_ms":percentile(elapsed,.95),"max_ms":max(elapsed),"throughput_per_second":round(len(rows)/span,4) if span else None,"error_percent":round(100*sum(r["success"]!="true" for r in rows)/len(rows),4)}
    return metrics


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--skip-jmeter",action="store_true")
    parser.add_argument("--only-jmeter",action="store_true")
    parser.add_argument("--only-ui",action="store_true",help="Re-run UI only, preserving completed API/JMeter run metadata.")
    parser.add_argument("--jmeter-home",type=Path,default=ROOT.parent/"tool-cache"/"apache-jmeter-5.6.3")
    args=parser.parse_args()
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    report={"scope":"Self-test on isolated local temporary database; not independent partner testing and not VPS measurements","started":stamp(),"training_bugs":True,"environment":{"os":platform.platform(),"python":sys.version,"cpu":platform.processor(),"logical_cpu_count":os.cpu_count(),"server":"Werkzeug threaded WSGI; not the deployed Gunicorn VPS"},"runs":{}}
    if args.only_ui and (EVIDENCE/"summary.json").exists():
        report=json.loads((EVIDENCE/"summary.json").read_text(encoding="utf-8"))
        report["ui_rerun_started"]=stamp()
    with tempfile.TemporaryDirectory(prefix="studentcare-tooling-") as temporary:
        application=create_app({"DATABASE":str(Path(temporary)/"support.db"),"TRAINING_BUGS":True,"SECRET_KEY":secrets.token_hex(32),"SESSION_COOKIE_SECURE":False})
        initialize(application,demo=True)
        server=make_server("127.0.0.1",0,application,threaded=True,request_handler=QuietHandler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f"http://127.0.0.1:{server.server_port}"
        report["base_url"]=base
        try:
            env={**os.environ,"BASE_URL":base}
            if not args.only_jmeter:
                scripts=[("puppeteer","puppeteer.cjs")] if args.only_ui else [("newman","run-newman.cjs"),("puppeteer","puppeteer.cjs")]
                for name,script in scripts:
                    print(f"Starting {name} on isolated data...",flush=True)
                    report["runs"][name]=run(["node",script],EVIDENCE/f"{name}.log",env)
                    print(name,report["runs"][name],flush=True)
            if not args.skip_jmeter and not args.only_ui:
                jar=args.jmeter_home/"bin"/"ApacheJMeter.jar"
                if not jar.exists():raise RuntimeError(f"Install Apache JMeter 5.6.3 outside repo: {jar}")
                report["jmeter_version"]=subprocess.check_output(["java","-jar",str(jar),"-v"],text=True,encoding="utf-8",errors="replace")
                report["java_version"]=subprocess.check_output(["java","-version"],stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
                for name,minimum in [("load",295),("step",355)]:
                    folder=EVIDENCE/f"jmeter-{name}"
                    if folder.exists():
                        folder=EVIDENCE/(f"jmeter-{name}-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
                    folder.mkdir(parents=True)
                    command=["java","-Xms128m","-Xmx512m","-jar",str(jar),"-n","-t",str(TOOLING/f"{name}.jmx"),"-l",str(folder/"results.jtl"),"-j",str(folder/"jmeter.log"),"-e","-o",str(folder/"dashboard"),f"-Jhost=127.0.0.1",f"-Jport={server.server_port}","-Jjmeter.save.saveservice.output_format=csv","-Jjmeter.save.saveservice.timestamp_format=ms","-Jjmeter.save.saveservice.print_field_names=true","-Jjmeter.save.saveservice.bytes=true","-Jjmeter.save.saveservice.thread_counts=true","-Jjmeter.save.saveservice.connect_time=true","-Jjmeter.save.saveservice.latency=true","-Jjmeter.save.saveservice.sent_bytes=true","-Jjmeter.save.saveservice.response_data=false"]
                    print(f"Starting native JMeter {name}: {300 if name=='load' else 360} actual seconds...",flush=True)
                    result=run(command,folder/"console.log",env)
                    if (folder/"results.jtl").exists():result["metrics"]=jtl_metrics(folder/"results.jtl")
                    result["configured_seconds"]=300 if name=="load" else 360
                    result["duration_verified"]=result["wall_seconds"]>=minimum
                    result["report"]=str((folder/"dashboard"/"index.html").relative_to(ROOT))
                    result["raw_results"]=str((folder/"results.jtl").relative_to(ROOT))
                    report["runs"][f"jmeter-{name}"]=result
                    (folder/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
                    (EVIDENCE/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                    print(name,result,flush=True)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=10)
            report["finished"]=stamp()
            (EVIDENCE/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Tool evidence recorded; assertion FAIL values remain FAIL.",flush=True)
    return 0 if all(value["exit_code"]==0 for value in report["runs"].values()) else 1


if __name__=="__main__":
    raise SystemExit(main())
