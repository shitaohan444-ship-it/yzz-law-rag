# VL 人工标注集放置说明

真实案件图片可能包含敏感信息，不提交到仓库。请在受控目录准备至少 30 张图片及
`manifest.json`，然后运行：

```powershell
python scripts/eval_vl.py D:\secure\vl-eval\manifest.json
```

正式集合至少包括：10 张 Logo/水印/装饰图、5 张印章或签名、5 张表格或流程图、
5 张截图或扫描正文、5 张证据照片。manifest 格式见 `scripts/eval_vl.py` 顶部说明。
