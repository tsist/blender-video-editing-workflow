# Blender 后期剪辑工作流

**0.2.0** 在 Blender 5.3 上增加受管批量精剪。一次请求可切分、移除或插入时间线片段，支持按组和整批回滚。

用于白膜分镜参考、AI 视频回流成片和 Blender 动画剪辑。源码包包含同一已验 CLI 快照、小型 VSE 插件核心、可移植配套技能与通用模板库。

**发行版 0.2.0｜插件 0.2.0｜模板库 0.1.0｜GPL-3.0-or-later**

- [安装与操作](docs/VIDEO-EDITING.md)：CLI、Blender 插件和技能分别如何使用。
- [批量精剪](docs/BATCH-EDITING.md)说明四种剪点定位、分组和整批回滚及可运行请求。
- [技能](skills/blender-video-editing/SKILL.md)：剪辑方法、镜头候选、字幕声音、人工往返及验收。
- [模板库](templates/video/README.md)：4 个预设、自定义模板与显式批量编译。
- [验证边界](docs/VALIDATION.md)：运行身份、发行校验与未验范围。

从发布页下载完整 source ZIP。插件 0.2.0 要求 Blender 5.3.0。在 Windows 上，可从源码根用随附 CLI 0.63.0 运行既有 `video` 操作。执行 `.\video-blenderctl.ps1 --blender $Blender video describe`，其中 `$Blender` 是可执行文件路径。批量精剪用公共 blenderctl v0.64.0 和其生产包 `1.0.0`，已验宿主为 Windows Blender 5.3.0。[剪辑发布页](https://github.com/tsist/blender-video-editing-workflow/releases) · [公共 CLI](https://github.com/tsist/blenderctl/releases/tag/v0.64.0)

独立安装技能或模板包时设置 `BLENDERCTL_ROOT` 为匹配源码根，不能只复制 CLI 单文件。插件 ZIP 用 Blender 的“从磁盘安装”入口安装；技能目录可复制到 agent 的技能目录，保留 references/scripts。

模板首版是 SDR 顺序硬切，编译只生成请求与回执，实际执行仍由公共 CLI 完成。完整回执、成功作业、独立重开与输出检查各自负责不同验收。字幕必须绑定合法可用的中文字体，最终观看产出判断可读性。

当前不提供 HLG、任意外来 VSE 接续、音频变速/非零声像、HDR 设备观看能力；4K HDR 高负载未通过验收。复杂演出和真实长片仍是未来验证目标。本包不包含个人工程、素材、运行缓存或第三方二进制。
