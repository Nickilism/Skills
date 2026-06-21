# Skills

个人自制的 [Minis](https://minis.dev) Skills 合集，分享给有需要的人。

## 什么是 Skill

Skill 是 Minis Agent 的可插拔能力模块——一份结构化的指令集，让 Agent 在特定场景下从"通用助手"变成"领域专家"。详见 [Minis Skill 文档](https://minis.dev/docs/skills)。

## Skills 列表

| Skill | 说明 | 依赖 |
|-------|------|------|
| [weread-anki](./weread-anki/) | 微信读书划线 → Anki 闪卡 | `weread` skill（API 模式需 `WEREAD_API_KEY`） |

## 安装方式

将 skill 目录复制到 Minis 的 skills 文件夹：

```
/var/minis/skills/<skill-name>/
```

或在 Minis 内通过 Agent 对话触发安装（如"帮我安装 weread-anki skill"）。

## 许可

MIT
