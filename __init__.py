# -*- coding: utf-8 -*-
"""Comfyui-K2-Editorial

Krea2「白垩光 / 未来奢华编辑主视觉」长文提示词的自动装配节点。
选角色 / 母题 / 画幅 / 服装 → 输出 1500–2700 词英文长提示词。

与 Anima-Wardrobe 的区别：白垩光是 25 段一体设计（一个母题决定整张画面），
不是 tag 随机池。所以这里是「母题整块 + 有限替换位」，不是池子自由组合。

素材来源：桌面 k2-baieguang / k2-chenxiguang 两个技能包 + MIKU-未来科幻风格 的
32 张成品图（内嵌提示词拆段成母题库）。

自包含：角色库 2432 条 / 角色图 2432 张 / 服装库 135 套（打包时快照）已内置在
`presets/anima/` 与 `thumbs/anima/`（共约 36 MB）。装了 Comfyui-Anima-Wardrobe-V6
时优先读实时数据（跟着它更新，当前 2432 角色 / 167 套服装），没装则自动回落到内置副本
—— 整个插件目录可单独拷走使用。
用 `K2ED_ANIMA_SOURCE=bundle|live|auto` 可强制切换（默认 auto）。
"""
from __future__ import annotations

__version__ = "1.17.3"

from .k2ed_node import K2EditorialBuilder, register_routes

NODE_CLASS_MAPPINGS = {
    "K2EditorialBuilder": K2EditorialBuilder,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "K2EditorialBuilder": "★ K2 长文出题 · 白垩光",
}
WEB_DIRECTORY = "./js"

register_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY",
           "__version__"]

print(f"[K2-Editorial] v{__version__} 已加载：{list(NODE_CLASS_MAPPINGS)}")
