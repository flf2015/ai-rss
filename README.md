# 国产 AI 官方信号 RSS

GitHub Actions 每 3 小时抓取一次公开更新，生成四个可由 Miniflux 订阅的 RSS 2.0 文件。无需 NAS、数据库、Cookie 或常驻浏览器。

## 订阅地址

仓库地址：[flf2015/ai-rss](https://github.com/flf2015/ai-rss)，默认分支 main：

| Feed | 用途 | GitHub Raw 地址 |
| --- | --- | --- |
| 重大官方动态 | 模型发布、开源、API 与价格等重要变化 | https://raw.githubusercontent.com/flf2015/ai-rss/main/feeds/china-ai-official.xml |
| Hugging Face 新模型 | 官方组织新建的模型仓库 | https://raw.githubusercontent.com/flf2015/ai-rss/main/feeds/china-ai-huggingface.xml |
| TokenHub 模型雷达 | 腾讯云 TokenHub 新增支持的模型 | https://raw.githubusercontent.com/flf2015/ai-rss/main/feeds/tokenhub-models.xml |
| Hugging Face Daily Papers | 每日收录的研究论文，含英文标题与摘要 | https://raw.githubusercontent.com/flf2015/ai-rss/main/feeds/huggingface-daily-papers.xml |

## 覆盖范围

重大官方动态抓取 [Qwen Research](https://qwen.ai/research)、[Kimi Research Blog](https://www.kimi.com/en/blog/)、[Kimi 开放平台 Blog](https://platform.kimi.com/blog)、[MiniMax Blog](https://www.minimax.io/blog)、[智谱模型与产品发布记录](https://docs.bigmodel.cn/cn/update/new-releases)、[DeepSeek API 更新日志](https://api-docs.deepseek.com/zh-cn/updates/) 和 [腾讯云 TokenHub 产品动态](https://cloud.tencent.com/document/product/1823/130675) 中的 HY 条目。

Hugging Face Feed 使用其[官方模型 API](https://huggingface.co/docs/hub/api)，监控 Qwen、deepseek-ai、moonshotai、MiniMaxAI、zai-org、tencent、XiaomiMiMo 七个组织。它只按 createdAt 判断新仓库，不把 README 或模型卡修改当成新发布。tencent 只保留 Hy/Hunyuan 模型，默认排除常见量化、演示和基准仓库。小米 MiMo 在首版由其官方 Hugging Face 组织和 TokenHub 雷达覆盖；小米官网 Blog 没有稳定的文章链接和发布日期数据，因此没有伪造发布时间写进重大动态。

TokenHub 雷达来自[腾讯云产品动态](https://cloud.tencent.com/document/product/1823/130675)。它表示模型进入该平台的时间，不等于厂商首次发布的时间。

Daily Papers Feed 来自 [Hugging Face Papers](https://huggingface.co/papers) 的[官方 Daily Papers API](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api#huggingface_hub.HfApi.list_daily_papers)。它独立收录页面的每日论文，未限定中国机构或厂商。每条以论文加入 Daily Papers 的日期排序，链接到 Hugging Face 论文页，摘要保留英文原文的前 500 个字符；不会因为票数变化重复发布。

## 自动更新

工作流每 3 小时运行，也可以在仓库 Actions 页面手动运行 Update AI RSS。将上表的 Raw 地址添加到 Miniflux 即可订阅。

工作流明确设置 contents: write，用于提交更新后的 XML。如果组织或仓库策略仍限制 GITHUB_TOKEN 写入，请在仓库的 Actions 设置中允许工作流读写。GitHub 的定时任务以 UTC 运行，可能有延迟；本项目不是精确的实时告警服务。

## 本地运行

需要 Python 3.12 或更新版本：

~~~bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_all.py
~~~

生成文件位于 feeds/。重复运行不会因为抓取时间改变 XML。单个网站抓取失败时会在日志中显示 WARN，并保留已有条目；所有来源都失败时脚本报错且不覆盖旧 Feed。XML 保留最近 120 天官方动态、45 天 Hugging Face 模型、120 天 TokenHub 更新和 14 天 Daily Papers，每条最多 100 项。Daily Papers 每次读取最近五个 UTC 日期，以覆盖周末和调度延迟。站点改版后，优先检查 Actions 日志中的来源错误。

## 筛选规则

重大官方动态先按标题过滤活动、教程、招聘等内容，再保留模型、开源、API、价格、Agent、Coding 与多模态等信号。这是可审查的关键词规则，不会生成未经证实的 AI 摘要。不同来源的同一事件可能各出现一次，例如厂商公告和 TokenHub 上线；它们代表不同的实际事件。需要调整过滤词时，修改 run_all.py 顶部的 NEGATIVE 与 POSITIVE。

所有链接指向来源页面；XML 只保留短摘要，不复制全文。仓库公开发布后，RSS 内容和提交历史也将公开。
