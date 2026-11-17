import numpy as np
import pytest

from backend.vision.ascend_service import decode_predictions


def predictions(rows):
    return np.asarray(rows,dtype=np.float32).T[None]


def test_nms_preserves_overlapping_different_classes():
    raw=predictions([[50,50,40,40,.9,.1],[50,50,40,40,.1,.8],[51,51,40,40,.85,.1]])
    result=decode_predictions(raw,['drone','light_bulb'],(100,100,3),1,(0,0))
    assert len(result)==2
    assert [row['label'] for row in result]==['drone','light_bulb']
    assert result[0]['bbox']==[30,30,70,70]


def test_letterbox_is_reversed_and_boxes_clipped_to_image():
    # Original 200x100 image scaled by 2 and padded 100 pixels vertically.
    raw=predictions([[200,200,400,200,.9],[0,0,1,1,.95]])
    result=decode_predictions(raw,['drone'],(100,200,3),2,(0,100))
    assert len(result)==1
    assert result[0]['bbox']==[0,0,199,99]


def test_invalid_class_mapping_and_nonfinite_scores_cannot_produce_results():
    with pytest.raises(ValueError):
        decode_predictions(np.zeros((1,6,4)),['only_one'],(100,100,3),1,(0,0))
    raw=predictions([[50,50,40,40,float('nan')],[50,50,40,40,.1]])
    assert decode_predictions(raw,['drone'],(100,100,3),1,(0,0))==[]
