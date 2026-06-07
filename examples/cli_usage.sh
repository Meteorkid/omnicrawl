#!/bin/bash
# OmniCrawl CLI 使用示例

# 1. 基础抓取
omnicrawl fetch https://example.com

# 2. 输出为 Markdown
omnicrawl fetch https://example.com --format markdown

# 3. 使用 Camoufox 模式绕过阿里云 WAF
omnicrawl fetch https://51job.com --mode camoufox --waf aliyun_waf

# 4. 使用预设
omnicrawl fetch https://example.com --preset stealth

# 5. 自定义请求头
omnicrawl fetch https://example.com \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  -H "Accept-Language: zh-CN,zh;q=0.9"

# 6. 批量抓取
echo "https://example.com/page1" > urls.txt
echo "https://example.com/page2" >> urls.txt
echo "https://example.com/page3" >> urls.txt
omnicrawl batch urls.txt --concurrency 5 --format json --output results/

# 7. HTML 转 Markdown
omnicrawl convert page.html --from html --to markdown

# 8. 查看配置
omnicrawl config

# 9. 查看预设配置
omnicrawl config --preset stealth

# 10. 版本信息
omnicrawl version
