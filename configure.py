from pathlib import Path
import shutil

assets_dir = Path(__file__).parent.resolve() / "assets"

def configure_ocr_model():
    # 检查源 OCR 资源主目录是否存在
    assets_ocr_dir = assets_dir / "MaaCommonAssets" / "OCR"
    if not assets_ocr_dir.exists():
        print(f"File Not Found: {assets_ocr_dir}")
        exit(1)

    # 【修改 1】：将目标路径更改为 assets/resource/base
    ocr_dir = assets_dir / "resource" / "base"/ "model"/ "ocr"
    
    print(f"正在将 OCR 模型 (ppocr_v4) 复制到: {ocr_dir} ...")
    
    # 【修改 2 & 3】：移除 if 判断强制覆盖，并将源路径改为 ppocr_v4/zh_cn
    shutil.copytree(
        assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v4" / "zh_cn",
        ocr_dir,
        dirs_exist_ok=True,  # 允许目标目录存在，这会直接覆盖/追加里面的文件
    )
    
    print("✅ OCR 模型复制完成！")

if __name__ == "__main__":
    configure_ocr_model()
    print("OCR model configured.")