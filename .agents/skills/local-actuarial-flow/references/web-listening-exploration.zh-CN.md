# web-listening 公开来源探索

使用隔离安装的 web-listening 3.3.0 做有界的手动来源故障调查。可执行文件固定在：

```powershell
$exploreCli = 'C:\Project\AI_actuarial_inforsearch\reports\local-automation-tools\web-listening-3.3.0\venv\Scripts\web-listening.exe'
```

这是独立 Python 3.12 环境，不使用或升级全局 web-listening。先读实际命令参数：

```powershell
& $exploreCli list-exploration-tools --json
& $exploreCli read-page --help
& $exploreCli download-file --help
& $exploreCli extract-pdf --help
& $exploreCli collect --help
```

输出目录应在本机调查证据目录下，为每次调查使用单独目录。显式提供允许的主机和较小的请求、响应字节上限；浏览器模式会将页面资源请求也计入 `--max-requests`。

```powershell
& $exploreCli read-page --url 'https://www.e-caa.org.cn/' --method http --output-dir $outDir --allowed-domain www.e-caa.org.cn --timeout-seconds 30 --max-http-bytes 2097152 --json
& $exploreCli read-page --url 'https://www.e-caa.org.cn/' --method browser --browser-channel chrome --output-dir $outDir --allowed-domain www.e-caa.org.cn --max-requests 30 --max-dom-bytes 2097152 --max-http-bytes 2097152 --json
& $exploreCli download-file --url $fileUrl --output-dir $outDir --allowed-domain $fileHost --max-bytes 20971520 --json
& $exploreCli extract-pdf --input $pdfPath --output-dir $outDir --json
& $exploreCli collect --urls-file $urlList --kind page --method http --output-dir $outDir --allowed-domain www.e-caa.org.cn --json
```

`read-page` 支持 `http` 或 `browser`；浏览器可显式选 `bundled`、`chromium`、`chrome` 或 `msedge`，还可用 `--actions-file` 传入有限页面动作。`collect` 可以增加 `--manifest`，并按需要用 `--parse-pdf` 保存 PDF 提取结果。不要让探索工具自动扩展为计划任务或无人值守抓取。

HTTP 示例是一条显式页面读取；`--max-requests` 只限制浏览器路线，HTTP 路线以单条命令、超时和响应字节上限控制。浏览器上限包含页面资源请求。浏览器诊断记录可能包含被拦截的请求尝试，尝试记录数不等于实际发出的 HTTP 请求数。

这些命令只生成本地探索证据。它们不调用本仓库的生产 bounded crawler，也不应用生产 crawler 的站点 host/path 白名单和每站 30 HTTP 请求预算；探索 CLI 本身也不继承 formal AccessGateway 控制。它们不写每日 v2 回执、Content Hub、China/Overseas 服务或 case ledger，因此探索成功不能计入每日来源、入库、AI 首类或同步成功。探索结论须保留命令 JSON、输出文件及原始错误，并单独写入研究记录。

已验证的 3.3.0 能通过 HTTP 与 Chrome 读取公开 CAA 页面、下载并提取本地 PDF，以及生成单 URL `collect` manifest。该验证只证明隔离工具可用，不改变生产抓取器的 30 请求上限或来源回执合同。
