"""采集命令行入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from flightmap_schema import load_sources

from .faa import FaaDiscovery

app = typer.Typer(help="Flight Map 官方航空资料采集工具")


@app.callback()
def main() -> None:
    """发现和校验官方数据；默认不下载、不发布。"""


@app.command("discover-faa")
def discover_faa(
    registry: Annotated[Path, typer.Option(exists=True, readable=True)] = Path(
        "sources/us/faa.yml"
    ),
    dry_run: Annotated[bool, typer.Option(help="仅发现链接，不下载资产")] = True,
    allow_network_failure: Annotated[
        bool, typer.Option(help="CI 定时探测时记录网络失败但不发布")
    ] = False,
) -> None:
    """扫描 FAA 官方产品页；该命令从不提升发布集。"""

    if not dry_run:
        raise typer.BadParameter("首期只允许 dry-run；资产采集必须由显式审核任务触发")

    discovery = FaaDiscovery()
    results: list[dict[str, object]] = []
    failed = False
    for source in load_sources(registry):
        for product in source.products:
            try:
                candidates = discovery.fetch(product)
                results.append(
                    {
                        "source": source.id,
                        "product": product.id,
                        "landing_page": str(product.landing_page),
                        "candidate_count": len(candidates),
                        "candidates": [candidate.__dict__ for candidate in candidates],
                        "promotion": "disabled",
                    }
                )
            except Exception as exc:  # 网络探测需要完整记录产品级失败
                failed = True
                results.append(
                    {
                        "source": source.id,
                        "product": product.id,
                        "landing_page": str(product.landing_page),
                        "error": str(exc),
                        "promotion": "disabled",
                    }
                )

    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    if failed and not allow_network_failure:
        raise typer.Exit(code=1)
