"""
变更日志生成器配置
"""

# 历史版本配置
HISTORY_CONFIG = {
    'max_historical_versions': 10,      # 最大历史版本数
    'enable_version_highlights': True,  # 启用版本标记
    'show_bot_accounts': True,          # 显示机器人账号
    'coauthor_display': True,           # 显示共同作者
}

# 输出格式配置
OUTPUT_CONFIG = {
    'include_build_info': True,         # 包含构建信息
    'include_cdk_link': True,           # 包含CDK链接
    'group_commits': True,              # 分组提交
}

# GitHub API配置
GITHUB_CONFIG = {
    'timeout': 30,                      # API超时时间
    'max_retries': 3,                   # 最大重试次数
}