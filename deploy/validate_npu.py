"""Evaluate a compiled OM against a small YOLO-labelled image directory.

This reports precision/recall at one confidence and IoU threshold, not mAP.
Use the full training report for validation-set metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.vision.ascend_service import AscendYolo


def overlap(a,b):
    left,top=max(a[0],b[0]),max(a[1],b[1])
    right,bottom=min(a[2],b[2]),min(a[3],b[3])
    intersection=max(0,right-left)*max(0,bottom-top)
    union=max(0,a[2]-a[0])*max(0,a[3]-a[1])+max(0,b[2]-b[0])*max(0,b[3]-b[1])-intersection
    return intersection/union if union else 0.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--confidence',type=float,default=.5)
    args=parser.parse_args()
    model=AscendYolo(args.model)
    counts={name:{'tp':0,'fp':0,'fn':0,'images':0} for name in model.names.values()}
    times=[]
    images=[]
    try:
        for image_path in sorted((args.data/'images').glob('*')):
            frame=cv2.imread(str(image_path))
            if frame is None:
                raise ValueError(f'Cannot read evaluation image: {image_path.name}')
            height,width=frame.shape[:2]
            target=[]
            for line in (args.data/'labels'/(image_path.stem+'.txt')).read_text().splitlines():
                cid,x,y,w,h=map(float,line.split())
                target.append({'class':model.names[int(cid)],'bbox':[(x-w/2)*width,(y-h/2)*height,(x+w/2)*width,(y+h/2)*height]})
            for name in {t['class'] for t in target}:
                counts[name]['images']+=1
            start=time.monotonic()
            predictions=model.detect(frame,args.confidence)
            times.append((time.monotonic()-start)*1000)
            unmatched=set(range(len(target)))
            for prediction in predictions:
                candidates=[(overlap(prediction['bbox'],target[i]['bbox']),i) for i in unmatched if target[i]['class']==prediction['label']]
                best=max(candidates,default=(0,None))
                matched=best[0]>=.5
                counts[prediction['label']]['tp' if matched else 'fp']+=1
                if matched:unmatched.remove(best[1])
            for index in unmatched:counts[target[index]['class']]['fn']+=1
            images.append({'file':image_path.name,'predictions':predictions})
    finally:
        model.close()
    if not times:
        raise ValueError('No labelled images evaluated')
    for row in counts.values():
        row['precision']=row['tp']/(row['tp']+row['fp']) if row['tp']+row['fp'] else 0.
        row['recall']=row['tp']/(row['tp']+row['fn']) if row['tp']+row['fn'] else 0.
    report={'images':len(times),'confidence':args.confidence,'iou':.5,'type':'fixed_threshold_sanity_check_not_mAP',
        'model_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),'classes':counts,
        'mean_ms':round(statistics.mean(times),2),'median_ms':round(statistics.median(times),2),'samples':images}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
