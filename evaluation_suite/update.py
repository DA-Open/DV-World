from huggingface_hub import HfApi

api = HfApi()

# 配置参数
repo_id = "Mjx0221/DV-World"  # 仓库ID
file_path = "/mnt/bn/mjx11/mlx/users/mengjinxiang/repo/DVSheet-1/evaluation_suite/results.zip"  # 本地文件路径

try:
    # 上传文件
    api.upload_file(
        path_or_fileobj=file_path,  # 本地文件路径
        path_in_repo="results.zip",   # 上传后的路径，默认根目录即可
        repo_id=repo_id,             # 仓库ID
        repo_type="dataset"          # 数据集类型
    )
    print(f"✅ 上传成功: {file_path}")
except Exception as e:
    print(f"❌ 上传出错: {e}")