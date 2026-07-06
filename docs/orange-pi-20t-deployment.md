# Orange Pi AIpro 20T Deployment Notes

The planned upper computer is Orange Pi AIpro 20T. Official Orange Pi material
lists the board with 20 TOPS AI compute, 12 GB or 24 GB LPDDR4X memory, eMMC and
M.2 storage options, dual 2.5G Ethernet, Wi-Fi 5, Bluetooth 4.2, HDMI, MIPI CSI,
and a 40-pin GPIO header.

## Practical Route

1. Develop and verify the complete software pipeline on Windows or a laptop.
2. Run the same Python backend on Orange Pi CPU first.
3. Use low-resolution inference such as 640x480 or 640x640 for the demo.
4. Export YOLO to ONNX after the pipeline is stable.
5. Try Ascend CANN/ATC conversion only after the CPU path is already working.

## Why This Order

The 20T NPU is attractive, but the Ascend toolchain is more specialized than the
normal PyTorch/Ultralytics workflow. For a short course project, the safest demo
path is:

```text
working pipeline first -> ONNX export -> NPU optimization if time remains
```

## Hardware Interface Choices

Recommended from easiest to hardest:

1. HTTP from microcontroller/IoT board to backend
2. MQTT between backend and hardware controller
3. USB serial protocol
4. direct GPIO from Orange Pi

For team integration, define a tiny command contract early:

```json
{"target":"light","action":"set","value":80}
{"target":"fan","action":"on"}
{"target":"door","action":"open"}
```
