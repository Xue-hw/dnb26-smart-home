"""Audit and refine the existing three-class model without replacing releases.

Run with the isolated .venv-train-bulb interpreter. No live camera is read.
Training negatives require an explicit, visually reviewed list from train only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def class_ids(label):
    return {int(row.split()[0]) for row in label.read_text(encoding='utf-8').splitlines() if row.strip()}


def weighted_training_paths(paths, labels, approved_negatives, bulb_repeat=3):
    if not approved_negatives <= set(paths) or any(2 in labels[p] for p in approved_negatives):
        raise ValueError('Approved negatives must be non-bulb images from the training split')
    return [path for path in paths for _ in range(bulb_repeat if 2 in labels[path] or path in approved_negatives else 1)]


def mine(args):
    from ultralytics import YOLO
    from PIL import Image, ImageDraw

    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    paths = sorted((args.source / 'images/train').glob('*'))
    candidates = [p for p in paths if 2 not in class_ids(args.source / 'labels/train' / (p.stem + '.txt'))]
    model = YOLO(str(args.checkpoint))
    found = []
    for start in range(0, len(candidates), 8):
        batch = candidates[start:start + 8]
        for path, result in zip(batch, model.predict(source=[str(p) for p in batch], stream=True,
                                                    imgsz=640, batch=8, conf=.35, classes=[2], device=0,
                                                    verbose=False, save=False)):
            if len(result.boxes):
                found.append({'path': str(path.resolve()), 'confidence': float(result.boxes.conf.max()),
                              'boxes': result.boxes.xyxy.cpu().tolist()})
        if start % 200 == 0:
            print(f'mining {start}/{len(candidates)} candidates={len(found)}', flush=True)
    found.sort(key=lambda row: row['confidence'], reverse=True)
    write_json(output / 'mined.json', {'checkpoint_sha256': sha256(args.checkpoint), 'source': str(args.source),
                                      'scanned_training_images': len(candidates), 'candidates': found,
                                      'warning': 'Not ground truth; visually inspect before approving negatives'})
    for page in range((min(len(found), 96) + 23) // 24):
        sheet = Image.new('RGB', (1200, 1056), 'white')
        draw = ImageDraw.Draw(sheet)
        for position, row in enumerate(found[page * 24:(page + 1) * 24]):
            image = Image.open(row['path']).convert('RGB')
            image.thumbnail((194, 228))
            x, y = (position % 6) * 200, (position // 6) * 264
            sheet.paste(image, (x, y))
            draw.text((x + 2, y + 230), f"#{page*24+position} score={row['confidence']:.3f}", fill='black')
        sheet.save(output / f'mining-sheet-{page}.jpg')
    print(f'mining finished: {len(found)} potential negatives; review sheets before training', flush=True)


def prepare(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    approved = set()
    if args.approved_negatives:
        approved = {Path(p).resolve() for p in json.loads(args.approved_negatives.read_text(encoding='utf-8'))}
    paths = sorted(p.resolve() for p in (args.source / 'images/train').glob('*'))
    labels = {p: class_ids(args.source / 'labels/train' / (p.stem + '.txt')) for p in paths}
    weighted = weighted_training_paths(paths, labels, approved)
    dataset = output / 'dataset'
    manifest = []
    for split in ('train', 'val', 'test'):
        (dataset / 'images' / split).mkdir(parents=True)
        (dataset / 'labels' / split).mkdir(parents=True)
        for path in sorted((args.source / 'images' / split).glob('*')):
            target = dataset / 'images' / split / path.name
            shutil.copy2(path, target)
            label = args.source / 'labels' / split / (path.stem + '.txt')
            shutil.copy2(label, dataset / 'labels' / split / label.name)
            manifest.append({'split': split, 'name': path.name, 'image_sha256': sha256(path), 'label_sha256': sha256(label)})
    crop_paths = []
    crop_spec = getattr(args, 'approved_crops', None)
    if crop_spec:
        from PIL import Image
        for index, spec in enumerate(json.loads(crop_spec.read_text(encoding='utf-8'))):
            path = Path(spec['source']).resolve()
            if path not in approved:
                raise ValueError('A reviewed crop must originate in approved train negatives')
            image = Image.open(path).convert('RGB')
            left, top, right, bottom = spec['box']
            if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                raise ValueError('Crop extends outside its source image')
            for row in (args.source/'labels/train'/(path.stem+'.txt')).read_text().splitlines():
                if not row.strip():
                    continue
                _, x, y, w, h = map(float, row.split())
                if min(right,(x+w/2)*image.width)>max(left,(x-w/2)*image.width) and min(bottom,(y+h/2)*image.height)>max(top,(y-h/2)*image.height):
                    raise ValueError('Negative crop intersects an existing target annotation')
            target = dataset/'images/train'/f'reviewed_negative_crop_{index}.jpg'
            image.crop((left,top,right,bottom)).save(target, quality=95)
            label = dataset/'labels/train'/(target.stem+'.txt')
            label.write_bytes(b'')
            crop_paths.append(target.resolve())
            manifest.append({'split':'train','name':target.name,'image_sha256':sha256(target),'label_sha256':sha256(label),
                             'derived_from_train':str(path),'crop_box':spec['box'],'review_note':spec['review_note']})
    hashes = {split: {r['image_sha256'] for r in manifest if r['split'] == split} for split in ('train', 'val', 'test')}
    if any(hashes[a] & hashes[b] for a, b in (('train', 'val'), ('train', 'test'), ('val', 'test'))):
        raise ValueError('Exact image hash leakage across inherited dataset splits')
    train_list = [str((dataset / 'images/train' / p.name).resolve()).replace('\\', '/') for p in weighted]
    train_list += [str(p).replace('\\','/') for p in crop_paths for _ in range(12)]
    (dataset / 'train.txt').write_bytes(('\n'.join(train_list) + '\n').encode('utf-8'))
    data = {'path': str(dataset.resolve()).replace('\\', '/'), 'train':'train.txt', 'val':'images/val',
            'test':'images/test', 'names':{0:'drone',1:'fire_extinguisher',2:'light_bulb'}}
    # JSON is valid YAML and preserves Windows paths without YAML escapes.
    write_json(dataset / 'data.yaml', data)
    write_json(output / 'dataset-manifest.json', {'source': str(args.source), 'samples': manifest,
        'training_entries': len(train_list), 'training_unique': len(paths)+len(crop_paths), 'approved_negatives': sorted(map(str, approved)),
        'original_split_preserved': True, 'current_person_capture': False})
    return dataset / 'data.yaml'


def match_counts(predictions, targets):
    used = set()
    true_positive = 0
    for prediction in predictions:
        best, best_iou = None, 0.
        for index, target in enumerate(targets):
            if index in used:
                continue
            intersection = max(0, min(prediction[2],target[2])-max(prediction[0],target[0])) * max(0, min(prediction[3],target[3])-max(prediction[1],target[1]))
            area = (prediction[2]-prediction[0])*(prediction[3]-prediction[1]) + (target[2]-target[0])*(target[3]-target[1])
            iou = intersection / (area-intersection) if area > intersection else 0.
            if iou > best_iou:
                best, best_iou = index, iou
        if best is not None and best_iou >= .5:
            used.add(best)
            true_positive += 1
    return true_positive, len(predictions)-true_positive, len(targets)-true_positive


def inference_floor():
    import numpy as np
    return float(np.nextafter(np.float32(.5), np.float32('-inf')))


def threshold_predictions(detections, cls, threshold):
    import numpy as np
    cutoff = float(np.float32(threshold))
    return [row[:4] for row in detections if row[4] >= cutoff and int(row[5]) == cls]


def fixed_metrics(model, dataset, split, output):
    paths = sorted((dataset / 'images' / split).glob('*'))
    listing = output / f'{split}-predict.txt'
    listing.write_bytes(('\n'.join(str(p.resolve()).replace('\\','/') for p in paths)+'\n').encode('utf-8'))
    counts = {threshold: {str(c): [0,0,0] for c in range(3)} for threshold in (.5,.7)}
    for result in model.predict(source=str(listing), stream=True, imgsz=640, batch=8, conf=inference_floor(),
                                iou=.6, device=0, verbose=False, save=False):
        height, width = result.orig_shape
        targets = {c: [] for c in range(3)}
        for line in (dataset/'labels'/split/(Path(result.path).stem+'.txt')).read_text().splitlines():
            if not line.strip():
                continue
            cls, x, y, w, h = map(float, line.split())
            targets[int(cls)].append([(x-w/2)*width,(y-h/2)*height,(x+w/2)*width,(y+h/2)*height])
        detections = sorted(result.boxes.data.cpu().tolist(),key=lambda row:row[4],reverse=True)
        for threshold in counts:
            for cls in range(3):
                predictions = threshold_predictions(detections, cls, threshold)
                outcome = match_counts(predictions, targets[cls])
                counts[threshold][str(cls)] = [a+b for a,b in zip(counts[threshold][str(cls)],outcome)]
    return {str(threshold): {cls:{'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else 0.,
                                    'recall':tp/(tp+fn) if tp+fn else 0.}
                              for cls,(tp,fp,fn) in values.items()} for threshold,values in counts.items()}


def train(args):
    import torch
    import ultralytics
    from ultralytics import YOLO
    from scripts.train_drone_fire_bulb_yolo import metrics_summary, verify_onnx

    if not torch.cuda.is_available():
        raise RuntimeError('Isolated CUDA training environment required')
    if args.prepared_data:
        args.output.mkdir(parents=True, exist_ok=False)
        data = args.prepared_data.resolve()
        if not data.is_file():
            raise FileNotFoundError(data)
    else:
        data = prepare(args)
    report = {'created_at':datetime.now(timezone.utc).isoformat(), 'source_checkpoint':str(args.checkpoint),
              'source_sha256':sha256(args.checkpoint), 'data':str(data), 'epochs_requested':args.epochs,
              'torch':torch.__version__, 'ultralytics':ultralytics.__version__, 'current_person_capture':False}
    report['metric_protocol'] = {'validation_and_test':'Ultralytics AP and P/R at library-selected work point',
        'fixed_validation_and_test':'raw TP/FP/FN at confidence .50/.70; class-aware IoU >= .50; NMS IoU .60',
        'negative_crops':'derived from same existing training scene, not independent evaluation samples',
        'specific_user_ears_glasses':'not captured or independently evaluated'}
    write_json(args.output / 'report.json', report)
    model = YOLO(str(args.checkpoint))
    report['baseline_validation'] = metrics_summary(model.val(data=str(data), imgsz=640, batch=8, device=0, workers=0,
        project=str(args.output), name='baseline-validation', plots=False, verbose=False))
    report['baseline_fixed_validation'] = fixed_metrics(model, data.parent, 'val', args.output)
    write_json(args.output / 'report.json', report)
    # Validation/prediction can fuse Conv/BatchNorm in place. Reload the original
    # unfused checkpoint before transferring weights into the training network.
    del model
    torch.cuda.empty_cache()
    model = YOLO(str(args.checkpoint))
    model.train(data=str(data), epochs=args.epochs, imgsz=640, batch=8, workers=0, device=0,
                project=str(args.output), name='train', seed=26, deterministic=True, patience=5,
                optimizer='AdamW', lr0=.0003, lrf=.1, warmup_epochs=1, warmup_bias_lr=.0003,
                close_mosaic=3, mosaic=.5,
                cache=False, amp=True, plots=True)
    checkpoint = Path(model.trainer.best)
    best = YOLO(str(checkpoint))
    if best.names != {0:'drone',1:'fire_extinguisher',2:'light_bulb'}:
        raise ValueError('Unexpected class mapping')
    report['candidate_validation'] = metrics_summary(best.val(data=str(data), imgsz=640, batch=8, device=0, workers=0,
        project=str(args.output), name='candidate-validation', plots=False, verbose=False))
    report['held_out_bulb_test'] = metrics_summary(best.val(data=str(data), split='test', imgsz=640, batch=8,
        device=0, workers=0, project=str(args.output), name='held-out-bulb-test', plots=False, verbose=False))
    baseline = YOLO(str(args.checkpoint))
    report['baseline_held_out_bulb_test'] = metrics_summary(baseline.val(data=str(data), split='test', imgsz=640, batch=8,
        device=0, workers=0, project=str(args.output), name='baseline-held-out-bulb-test', plots=False, verbose=False))
    report['candidate_fixed_validation'] = fixed_metrics(best, data.parent, 'val', args.output)
    report['baseline_fixed_test'] = fixed_metrics(baseline, data.parent, 'test', args.output)
    report['candidate_fixed_test'] = fixed_metrics(best, data.parent, 'test', args.output)
    report['checkpoint'] = {'path':str(checkpoint),'sha256':sha256(checkpoint)}
    write_json(args.output / 'report.json', report)
    onnx = Path(best.export(format='onnx',imgsz=640,opset=12,dynamic=False,simplify=False,device='cpu'))
    report['onnx'] = {'path':str(onnx),'sha256':sha256(onnx)}
    report['onnx_validation'] = verify_onnx(checkpoint, onnx)
    report['deployment_status'] = 'not_deployed_quality_review_required'
    write_json(args.output / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('mine','train'))
    parser.add_argument('--source', type=Path, default=ROOT / 'data/datasets/drone_fire_bulb_v2')
    parser.add_argument('--checkpoint',type=Path,default=ROOT / 'deploy_export/weights/dnb26_drone_fire_bulb_yolo11n_best.pt')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--approved-negatives',type=Path)
    parser.add_argument('--approved-crops',type=Path)
    parser.add_argument('--prepared-data',type=Path)
    parser.add_argument('--epochs',type=int,default=15)
    args = parser.parse_args()
    args.output = args.output.resolve()
    (mine if args.phase == 'mine' else train)(args)


if __name__ == '__main__':
    main()
