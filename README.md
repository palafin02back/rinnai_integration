# Rinnai采暖设备集成（HomeAssistant插件）

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/releases)
[![GitHub license](https://img.shields.io/github/license/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/blob/master/LICENSE)

此集成可让你在 Home Assistant 中控制和监控 Rinnai（林内）G56 系列锅炉采暖设备。

---

## ⚠️ 重要风险警示

**使用本集成存在被官方服务器封号的风险**。一旦被封号，可能导致在原厂 APP 内设备会一直显示离线，无法正常远程控制设备。  
**请在充分知晓风险、自愿承担责任的前提下使用本插件。严格不建议在主账号下使用。开发者及本开源项目对由此带来的损失不承担任何责任。**

---

## 功能特性

- 控制采暖温度
- 控制热水温度
- 切换采暖模式（正常模式 / 节能模式 / 户外模式）
- 查看设备状态及部分信息
- 支持锅炉开/关机操作
- 支持额外通过MQTT推送原始数据（数据含义未详尽）

## 安装方式

### 方法一：HACS安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 页面点击「自定义存储库」
3. 添加存储库 URL：`https://github.com/palafin02back/rinnai_integration`
4. 类别选择「集成」
5. 点击「添加」
6. 在 HACS 集成页面搜索「Rinnai」并安装

### 方法二：手动安装

1. 下载本仓库源码
2. 将 `custom_components/rinnai` 文件夹复制到 HomeAssistant 配置目录下的 `custom_components` 文件夹中
3. 重启 HomeAssistant

## 配置方法

支持通过 UI 图形界面配置：

1. 进入 HomeAssistant 配置 → 集成 → 添加集成
2. 搜索「Rinnai」
3. 按照页面向导完成配置参数填写

## 支持设备列表

- 主要支持林内采暖设备（G56系列）
- 其他系列暂未适配支持
- 已在 HomeAssistant `2025.2.0` 版本测试（其他版本请自行验证兼容性）

## 效果展示

- 温度控制界面示例  
  ![image](https://github.com/user-attachments/assets/64e9123e-0d23-42cf-8090-7f3f962a2086)  
  ![image](https://github.com/user-attachments/assets/5fa8d68a-017d-4def-9f90-961a55ab107a)  
  ![image](https://github.com/user-attachments/assets/12931304-33d3-42f3-b6a9-69cb367b50aa)

- MQTT 原始数据展示（原始数据仅供参考，具体意义未解析）

## 常见问题与故障排查

如遇问题，请逐项检查：

1. 设备是否已正确联网
2. 可否通过原厂 APP 正常控制
3. 查看 HomeAssistant 日志，检查是否有相关报错
4. 若无法解决，请开启调试日志，并在 issues 区提交问题时附带完整 HomeAssistant 版本及错误日志

## 贡献与支持

欢迎提交 Issue 或 PR 反馈问题与建议，协助本集成完善。

## 免责声明

本项目为非官方的爱好者开发项目，不受 Rinnai 官方支持或认证，仅限爱好者研究用途。由此带来封号、设备异常、数据丢失等风险由用户个人承担，开发者及维护者不对此承担任何责任。强烈建议慎重使用！

## 许可证

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
