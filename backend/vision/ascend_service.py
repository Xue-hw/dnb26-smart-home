"""Small synchronous ACL adapter for trusted, static YOLO11 OM models.

The model must have batch-one float32 NCHW input and a float32 [1,4+C,N]
output without embedded NMS. Metadata next to model.om is model.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading

import numpy as np


def check(code, operation):
    if code != 0:
        raise RuntimeError(f'Ascend {operation} failed (ACL {code})')


def decode_predictions(prediction, names, image_shape, ratio, pad, confidence=.4, iou=.45):
    """Undo letterboxing and perform class-aware NMS on raw YOLO scores."""
    import cv2
    array = np.asarray(prediction)
    if array.ndim != 3 or array.shape[0] != 1 or array.shape[1] != 4+len(names):
        raise ValueError('OM output does not match the declared YOLO class count')
    rows = array[0].T
    classes = rows[:,4:].argmax(axis=1)
    scores = rows[np.arange(len(rows)),4+classes]
    selected = np.isfinite(rows).all(axis=1) & (scores >= confidence)
    rows, classes, scores = rows[selected],classes[selected],scores[selected]
    if not len(rows):
        return []
    corners = rows[:,:4].copy()
    corners[:,:2] -= corners[:,2:4]/2
    corners[:,2:4] += corners[:,:2]
    corners[:,[0,2]] = (corners[:,[0,2]]-pad[0])/ratio
    corners[:,[1,3]] = (corners[:,[1,3]]-pad[1])/ratio
    height,width = image_shape[:2]
    corners[:,[0,2]] = np.clip(corners[:,[0,2]],0,width-1)
    corners[:,[1,3]] = np.clip(corners[:,[1,3]],0,height-1)
    detections = []
    for class_id in np.unique(classes):
        indices = np.flatnonzero(classes==class_id)
        boxes = corners[indices].copy()
        boxes[:,2:4] -= boxes[:,:2]
        valid = (boxes[:,2]>0) & (boxes[:,3]>0)
        indices,boxes = indices[valid],boxes[valid]
        if not len(indices):
            continue
        # OpenCV uses strict >; the >= score filter above owns the threshold.
        nms_threshold = max(0., float(np.nextafter(np.float32(confidence), np.float32(-np.inf))))
        kept = cv2.dnn.NMSBoxes(boxes.tolist(),scores[indices].tolist(),nms_threshold,float(iou))
        for index in np.asarray(kept,dtype=int).reshape(-1):
            source = indices[index]
            detections.append({'label':names[int(class_id)],'confidence':float(scores[source]),
                               'bbox':corners[source].astype(int).tolist()})
    return sorted(detections,key=lambda row:row['confidence'],reverse=True)


class AscendYolo:
    # ACL initialization belongs to the process, not to a model or inference thread.
    _guard = threading.RLock()
    _context = None
    _references = 0
    _acl = None

    def __init__(self, path):
        path = Path(path)
        metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        names = metadata['names']
        if isinstance(names,dict):
            names = [names[str(i)] if str(i) in names else names[i] for i in range(len(names))]
        if not isinstance(names,list) or not names or not all(isinstance(n,str) and n for n in names):
            raise ValueError('OM metadata must declare a nonempty ordered names list')
        self.names = dict(enumerate(names))
        self.buffers = []
        self.input_dataset = self.output_dataset = self.desc = self.model_id = None
        self.closed = False
        self.lock = threading.RLock()
        with self._guard:
            cls = type(self)
            if cls._references == 0:
                import acl
                check(acl.init(),'init')
                try:
                    check(acl.rt.set_device(0),'set device')
                    context,code = acl.rt.create_context(0)
                    check(code,'create context')
                except BaseException:
                    acl.finalize()
                    raise
                cls._acl,cls._context = acl,context
            cls._references += 1
        self.acl = type(self)._acl
        try:
            self._set_context()
            self.model_id,code = self.acl.mdl.load_from_file(str(path))
            check(code,'load model')
            self.desc = self.acl.mdl.create_desc()
            check(self.acl.mdl.get_desc(self.desc,self.model_id),'model description')
            if self.acl.mdl.get_num_inputs(self.desc)!=1 or self.acl.mdl.get_num_outputs(self.desc)!=1:
                raise ValueError('Only single-input/single-output YOLO OM models are supported')
            inp,code = self.acl.mdl.get_input_dims(self.desc,0)
            check(code,'input shape')
            out,code = self.acl.mdl.get_output_dims(self.desc,0)
            check(code,'output shape')
            self.input_shape,self.output_shape = tuple(inp['dims']),tuple(out['dims'])
            if (len(self.input_shape)!=4 or self.input_shape[:2]!=(1,3)
                    or min(self.input_shape)<=0 or self.input_shape[2]!=self.input_shape[3]
                    or len(self.output_shape)!=3 or self.output_shape[:2]!=(1,4+len(names))):
                raise ValueError('Expected static square NCHW YOLO input and [1,4+C,N] output')
            if self.acl.mdl.get_input_data_type(self.desc,0)!=0 or self.acl.mdl.get_output_data_type(self.desc,0)!=0:
                raise ValueError('OM input and output must both be float32')
            self.input_dataset,self.input_ptr = self._dataset(self.acl.mdl.get_input_size_by_index(self.desc,0))
            self.output_dataset,self.output_ptr = self._dataset(self.acl.mdl.get_output_size_by_index(self.desc,0))
            self.output = np.empty(self.output_shape,dtype=np.float32)
            if self.output.nbytes!=self.acl.mdl.get_output_size_by_index(self.desc,0):
                raise ValueError('Unexpected padded OM output buffer size')
        except BaseException:
            self.close()
            raise

    def _set_context(self):
        check(self.acl.rt.set_context(type(self)._context),'set thread context')

    def _dataset(self, size):
        dataset = self.acl.mdl.create_dataset()
        ptr,code = self.acl.rt.malloc(size,2)
        if code:
            self.acl.mdl.destroy_dataset(dataset)
            check(code,'allocate model buffer')
        buffer = self.acl.create_data_buffer(ptr,size)
        self.buffers.append((dataset,buffer,ptr))
        _,code = self.acl.mdl.add_dataset_buffer(dataset,buffer)
        check(code,'add model buffer')
        return dataset,ptr

    def raw(self, tensor):
        tensor = np.ascontiguousarray(tensor,dtype=np.float32)
        if tensor.shape!=self.input_shape:
            raise ValueError('Input tensor shape does not match compiled OM')
        with self.lock:
            if self.closed:
                raise RuntimeError('OM session is closed')
            self._set_context()
            check(self.acl.rt.memcpy(self.input_ptr,tensor.nbytes,int(tensor.ctypes.data),tensor.nbytes,1),'copy input')
            check(self.acl.mdl.execute(self.model_id,self.input_dataset,self.output_dataset),'execute')
            check(self.acl.rt.memcpy(int(self.output.ctypes.data),self.output.nbytes,self.output_ptr,self.output.nbytes,2),'copy output')
            return self.output.copy()

    def detect(self, image, confidence=.4):
        import cv2
        height,width = image.shape[:2]
        size = self.input_shape[2]
        ratio = min(size/height,size/width)
        resized_width,resized_height = round(width*ratio),round(height*ratio)
        left,top = (size-resized_width)//2,(size-resized_height)//2
        resized = cv2.resize(image,(resized_width,resized_height))
        boxed = np.full((size,size,3),114,dtype=np.uint8)
        boxed[top:top+resized_height,left:left+resized_width] = resized
        tensor = np.ascontiguousarray(boxed[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255.
        return decode_predictions(self.raw(tensor),list(self.names.values()),image.shape,ratio,(left,top),confidence)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self._set_context()
            for dataset,buffer,ptr in self.buffers:
                self.acl.destroy_data_buffer(buffer)
                self.acl.mdl.destroy_dataset(dataset)
                self.acl.rt.free(ptr)
            if self.model_id is not None:
                self.acl.mdl.unload(self.model_id)
            if self.desc is not None:
                self.acl.mdl.destroy_desc(self.desc)
            with self._guard:
                cls = type(self)
                cls._references -= 1
                if cls._references==0:
                    self.acl.rt.destroy_context(cls._context)
                    self.acl.rt.reset_device(0)
                    self.acl.finalize()
                    cls._context = cls._acl = None
