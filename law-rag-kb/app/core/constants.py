"""入库链状态枚举。

kb_document.embedding_status 与 sys_attachment.ai_index_status 复用同一套字符串。
该字段在数据库无冻结字典枚举，此处为代码级常量（不落 sys_dict_item）。
"""


class EmbeddingStatus:
    PENDING = "pending"  # 待入库
    PROCESSING = "processing"  # 入库中
    SUCCESS = "success"  # 入库成功
    FAILED = "failed"  # 入库失败（解析/下载/embedding/Milvus 异常）
    SKIPPED = "skipped"  # 跳过（不支持文件类型 / object_key 缺失 / 已入库未强制）
