"""OmniCrawl CLI — 命令行入口

用法:
    omnicrawl fetch https://example.com
    omnicrawl fetch https://example.com --mode browser --format markdown
    omnicrawl batch url1 url2 url3 --concurrency 5
    omnicrawl convert page.html --format markdown
    omnicrawl config show
    omnicrawl version
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer

from omnicrawl.fetchers.base import FetchMode

app = typer.Typer(
    name="omnicrawl",
    help="🕷️ OmniCrawl — 无所不能的爬虫框架，绕过 WAF，LLM 友好输出",
    no_args_is_help=True,
)

# 格式选项
FORMAT_OPTION = typer.Option(
    "markdown",
    "--format", "-f",
    help="输出格式: json, markdown, text, html",
)

# 模式选项
MODE_OPTION = typer.Option(
    "auto",
    "--mode", "-m",
    help="抓取模式: http, browser, camoufox, stealth, auto",
)


def _parse_mode(mode_str: str) -> FetchMode:
    """解析模式字符串为 FetchMode 枚举"""
    mapping = {m.value: m for m in FetchMode}
    mapping["auto"] = FetchMode.AUTO
    mode = mapping.get(mode_str.lower())
    if mode is None:
        raise typer.BadParameter(f"未知模式: {mode_str}，可选: {', '.join(mapping.keys())}")
    return mode


def _format_result(result, fmt: str) -> str:
    """格式化 FetchResult 输出"""
    if fmt == "json":
        data = {
            "url": result.url,
            "status_code": result.status_code,
            "ok": result.ok,
            "blocked": result.blocked,
            "mode_used": result.mode_used.value,
            "elapsed": round(result.elapsed, 3),
            "markdown": result.markdown,
            "text": result.text,
            "headers": dict(result.headers),
            "cookies": dict(result.cookies),
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    elif fmt == "markdown":
        return result.markdown or result.text or result.html or ""

    elif fmt == "text":
        return result.text or ""

    elif fmt == "html":
        return result.html or ""

    else:
        raise typer.BadParameter(f"未知格式: {fmt}，可选: json, markdown, text, html")


@app.command()
def fetch(
    url: str = typer.Argument(..., help="目标 URL"),
    mode: str = MODE_OPTION,
    fmt: str = FORMAT_OPTION,
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="超时时间（秒）"),
    header: list[str] = typer.Option([], "--header", "-H", help="自定义请求头 (key:value)"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址"),
    waf: Optional[str] = typer.Option(None, "--waf", "-w", help="WAF 策略名称"),
    fingerprint: str = typer.Option("chrome", "--fingerprint", help="TLS 指纹"),
    max_retries: int = typer.Option(2, "--retries", "-r", help="最大重试次数"),
    no_fallback: bool = typer.Option(False, "--no-fallback", help="禁用自动降级"),
    preset: Optional[str] = typer.Option(None, "--preset", help="使用配置预设"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """抓取单个 URL 并输出结果"""
    from omnicrawl.config import load_config, merge_cli_config, apply_config_to_client

    config_data = load_config()
    cli_args = {"mode": mode, "fingerprint": fingerprint, "waf": waf,
                "max_retries": max_retries, "timeout": timeout}
    merged = merge_cli_config(cli_args, config_data, preset=preset)

    fetch_mode = _parse_mode(merged.get("mode", "auto"))
    headers = _parse_headers(header)

    async def _run():
        from omnicrawl import OmniClient
        client_kwargs = apply_config_to_client(merged)
        client_kwargs["mode"] = fetch_mode
        client_kwargs["auto_fallback"] = not no_fallback

        async with OmniClient(**client_kwargs) as client:
            return await client.get(
                url,
                headers=headers or None,
                proxy=proxy or merged.get("proxy"),
                timeout=merged.get("timeout", 30.0),
            )

    result = asyncio.run(_run())
    text = _format_result(result, merged.get("format", fmt))

    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"✅ 已保存到 {output}")
    else:
        typer.echo(text)


@app.command()
def batch(
    urls: list[str] = typer.Argument(..., help="目标 URL 列表"),
    mode: str = MODE_OPTION,
    fmt: str = FORMAT_OPTION,
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="并发数"),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="超时时间（秒）"),
    header: list[str] = typer.Option([], "--header", "-H", help="自定义请求头 (key:value)"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址"),
    waf: Optional[str] = typer.Option(None, "--waf", "-w", help="WAF 策略名称"),
    preset: Optional[str] = typer.Option(None, "--preset", help="使用配置预设"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-d", help="输出目录（每个 URL 一个文件）"),
):
    """批量抓取多个 URL"""
    from omnicrawl.config import load_config, merge_cli_config, apply_config_to_client

    config_data = load_config()
    cli_args = {"mode": mode, "waf": waf, "timeout": timeout}
    merged = merge_cli_config(cli_args, config_data, preset=preset)

    fetch_mode = _parse_mode(merged.get("mode", "auto"))
    headers = _parse_headers(header)

    async def _run():
        from omnicrawl import OmniClient
        client_kwargs = apply_config_to_client(merged)
        client_kwargs["mode"] = fetch_mode

        async with OmniClient(**client_kwargs) as client:
            return await client.batch_with_errors(
                urls,
                concurrency=concurrency,
                headers=headers or None,
                proxy=proxy or merged.get("proxy"),
                timeout=merged.get("timeout", 30.0),
            )

    successes, errors = asyncio.run(_run())
    out_fmt = merged.get("format", fmt)

    # 输出成功结果
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    for i, result in enumerate(successes):
        text = _format_result(result, out_fmt)
        if output_dir:
            filename = _url_to_filename(result.url, i)
            filepath = output_dir / filename
            filepath.write_text(text, encoding="utf-8")
        else:
            typer.echo(f"--- [{result.status_code}] {result.url} ---")
            typer.echo(text)
            typer.echo()

    # 输出失败摘要
    if errors:
        typer.echo(f"\n❌ {len(errors)} 个 URL 抓取失败:", err=True)
        for url, exc in errors:
            typer.echo(f"  - {url}: {exc}", err=True)

    typer.echo(f"\n📊 成功: {len(successes)}, 失败: {len(errors)}, 总计: {len(urls)}")


@app.command(name="convert")
def convert_cmd(
    file: Path = typer.Argument(..., help="HTML 文件路径"),
    fmt: str = typer.Option("markdown", "--format", "-f", help="输出格式: markdown, text, json"),
    compact: bool = typer.Option(False, "--compact", help="紧凑模式（移除噪音）"),
    strip_links: bool = typer.Option(False, "--strip-links", help="移除链接"),
    strip_images: bool = typer.Option(False, "--strip-images", help="移除图片"),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="最大 token 数"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """将 HTML 文件转换为 Markdown"""
    if not file.exists():
        typer.echo(f"❌ 文件不存在: {file}", err=True)
        raise typer.Exit(1)

    html = file.read_text(encoding="utf-8")

    from omnicrawl import MarkdownConverter

    converter = MarkdownConverter(
        compact=compact,
        strip_links=strip_links,
        strip_images=strip_images,
        max_tokens=max_tokens,
    )

    if fmt == "json":
        stats = converter.convert_with_stats(html)
        text = json.dumps(stats, ensure_ascii=False, indent=2)
    elif fmt == "markdown":
        text = converter.convert(html)
    elif fmt == "text":
        # 先转 markdown，再做简单的去格式
        md = converter.convert(html)
        import re
        text = re.sub(r"[#*_`\[\]()~>|-]", "", md)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        raise typer.BadParameter(f"未知格式: {fmt}")

    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"✅ 已保存到 {output}")
    else:
        typer.echo(text)


@app.command()
def version():
    """显示版本信息"""
    from omnicrawl import __version__
    typer.echo(f"omnicrawl {__version__}")


@app.command()
def config(
    action: str = typer.Argument("show", help="操作: show, path"),
    preset: Optional[str] = typer.Option(None, "--preset", help="显示指定预设"),
):
    """查看配置信息"""
    from omnicrawl.config import find_config, load_config, get_default, get_preset

    if action == "path":
        path = find_config()
        if path:
            typer.echo(path)
        else:
            typer.echo("未找到配置文件", err=True)
            typer.echo("创建方法: 在项目目录或 ~ 下创建 omnicrawl.toml", err=True)
        return

    if action == "show":
        path = find_config()
        if path is None:
            typer.echo("📋 未找到配置文件，使用默认设置")
            typer.echo(f"搜索路径: {[str(p) for p in [Path.cwd() / 'omnicrawl.toml', Path.home() / 'omnicrawl.toml']]}")
            return

        config_data = load_config(path)
        typer.echo(f"📁 配置文件: {path}")
        typer.echo()

        # 默认配置
        defaults = get_default(config_data)
        if defaults:
            typer.echo("[default]")
            for k, v in defaults.items():
                typer.echo(f"  {k} = {v!r}")
            typer.echo()

        # 预设
        presets = config_data.get("presets", {})
        if presets:
            if preset:
                p = get_preset(config_data, preset)
                if p:
                    typer.echo(f"[presets.{preset}]")
                    for k, v in p.items():
                        typer.echo(f"  {k} = {v!r}")
                else:
                    typer.echo(f"❌ 预设 '{preset}' 不存在，可用: {', '.join(presets.keys())}")
            else:
                typer.echo("[presets]")
                for name, values in presets.items():
                    typer.echo(f"  {name} = {values}")
            typer.echo()

        return

    raise typer.BadParameter(f"未知操作: {action}，可选: show, path")


def _parse_headers(header_list: list[str]) -> dict[str, str]:
    """解析 header 列表 (key:value) 为字典"""
    headers = {}
    for h in header_list:
        if ":" not in h:
            raise typer.BadParameter(f"请求头格式错误: {h}，应为 key:value")
        key, value = h.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _url_to_filename(url: str, index: int) -> str:
    """将 URL 转换为安全的文件名"""
    import re
    # 移除协议前缀
    name = re.sub(r"^https?://", "", url)
    # 替换非字母数字字符
    name = re.sub(r"[^\w\-.]", "_", name)
    # 截断过长名称
    if len(name) > 100:
        name = name[:100]
    return f"{index:03d}_{name}.md"


def main():
    """入口点"""
    app()


if __name__ == "__main__":
    main()
