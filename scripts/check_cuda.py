"""检查当前 Python 环境中的 PyTorch CUDA 可用性。

用于确认训练环境能否识别 RTX 4060，以及 torch 是否为 CUDA 版本。
"""

from _project_path import add_project_root

add_project_root()


def main() -> None:
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("torch is not installed.") from exc

    print(f"torch: {torch.__version__}")
    print(f"cuda_available: {torch.cuda.is_available()}")
    print(f"torch_cuda: {torch.version.cuda}")
    print(f"device_count: {torch.cuda.device_count()}")
    if torch.cuda.is_available():
        print(f"device_0: {torch.cuda.get_device_name(0)}")


if __name__ == "__main__":
    main()
