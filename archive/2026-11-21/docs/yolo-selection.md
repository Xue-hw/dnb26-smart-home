# YOLO Selection

## Recommendation

Use YOLO11n as the default detector and keep YOLOv8n as a fallback.

YOLOv5 is still usable, but it is not the best default for this project because
your existing scripts already use the modern `ultralytics.YOLO` API. YOLO11n and
YOLOv8n also have a cleaner path for exporting models to ONNX and later trying
edge-device acceleration.

## Decision Table

| Option | Use it when | Risk |
| --- | --- | --- |
| YOLO11n | Main project path, new code, classroom demo | May need newer Ultralytics package |
| YOLOv8n | Compatibility fallback | Slightly older than YOLO11 |
| YOLOv5n/s | Existing YOLOv5 code must be reused | Older repo/API style |
| Custom fine-tuned YOLO11n | Bulb-picture trigger or custom home objects | Needs image labeling and training time |

## Development Plan

1. Run COCO pretrained `yolo11n.pt` for people and common objects.
2. Add API output storage for each detection event.
3. Collect 50-100 images if the bulb-trigger feature is required.
4. Fine-tune YOLO11n on the custom class.
5. Export ONNX and test on Orange Pi AIpro 20T.
