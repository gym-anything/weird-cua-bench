#!/usr/bin/env python3
"""Replay saved UI attempts through the exact static-browser Pyodide worker.

This grades existing artifacts; it does not solve tasks or run a CUA model.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

BENCH = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == '/':
            body=b'<!doctype html><title>Saved UI artifact verification</title><h1>Static grader verification</h1>'
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


def verify(records: list[Path], output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=False)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(BENCH/'shared_runtime')))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    results=[]
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/',wait_until='networkidle')
            page.evaluate('''() => {
                const worker = new Worker('/browser/grader_worker.js',{type:'module'});
                let sequence=0;
                const pending=new Map();
                worker.onmessage=({data})=>{
                    const slot=pending.get(data.id); if(!slot)return;
                    pending.delete(data.id); clearTimeout(slot.timer); slot.resolve(data);
                };
                worker.onerror=error=>{
                    for(const slot of pending.values()){
                        clearTimeout(slot.timer);slot.resolve({ok:false,error:error.message});
                    }
                    pending.clear();
                };
                window.gradeSavedAttempt=data=>new Promise(resolve=>{
                    const id=++sequence;
                    const timer=setTimeout(()=>{
                        pending.delete(id);resolve({ok:false,error:'static grader exceeded 60-second deadline'});
                    },60000);
                    pending.set(id,{resolve,timer});worker.postMessage({id,...data});
                });
            }''')
            for index,record_dir in enumerate(records):
                summary=json.loads((record_dir/'summary.json').read_text())
                exported=json.loads((record_dir/'exported.json').read_text())
                assert summary['status']=='passed' and summary['check']=='solve',record_dir
                mechanic=summary['mechanic']
                result=page.evaluate('data=>gradeSavedAttempt(data)',dict(
                    graderUrl=f'/server/incubator_graders/{mechanic}.py',payload=exported['result'],
                    groundTruth=exported['ground_truth'],publicState=exported['public_state'],
                ))
                passed=result.get('ok') is True and result.get('grade',{}).get('passed') is True
                results.append(dict(record=str(record_dir),mechanic=mechanic,passed=passed,result=result))
                if not passed:print(json.dumps(results[-1]),flush=True)
                if (index+1)%30==0:print(f'Pyodide artifacts: {index+1}/{len(records)}',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
    summary=dict(scope='saved native-UI artifact grading, not model evaluation',
                 worker='shared_runtime/browser/grader_worker.js',headless=True,fresh_browser_profile=True,
                 count=len(results),passed=sum(item['passed'] for item in results),records=results)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',action='append',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    summary=verify(args.record,args.out_dir)
    print(json.dumps({key:value for key,value in summary.items() if key!='records'},indent=2))
    raise SystemExit(0 if summary['count']==summary['passed'] else 1)


if __name__=='__main__':main()
